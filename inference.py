"""
inference.py — SQL Query Review Environment
============================================
MANDATORY (competition rules):
  - Named inference.py, placed at project ROOT
  - Uses OpenAI client for all LLM calls
  - Reads API_BASE_URL, MODEL_NAME, HF_TOKEN from environment variables
  - Emits exact [START] / [STEP] / [END] lines to stdout

Run:
    export HF_TOKEN=hf_...
    export API_BASE_URL=https://router.huggingface.co/v1
    export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
    python inference.py
"""
import asyncio
import os
import sys
import json
import textwrap
from typing import List, Optional

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "server"))

from openai import OpenAI
from client import SQLQueryReviewEnv
from models import SQLReviewAction

# ── Config — EXACT spec format ────────────────────────────────────────────────
# Defaults set only for API_BASE_URL and MODEL_NAME (per competition rules)
API_BASE_URL     = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
MODEL_NAME       = os.getenv("MODEL_NAME",   "Qwen/Qwen2.5-72B-Instruct")
# HF_TOKEN: NO default — must be set in environment
HF_TOKEN          = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
# LOCAL_IMAGE_NAME: optional, only needed if using from_docker_image()
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")

PORT             = os.getenv("PORT", "7860")
BENCHMARK        = "sql_query_review"
MAX_STEPS        = 1
TEMPERATURE      = 0.2
MAX_TOKENS       = 600
SUCCESS_SCORE_THRESHOLD = 0.4

# ── Mandatory log functions — exact format, no changes allowed ────────────────

def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)

def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val  = str(done).lower()
    print(f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}", flush=True)

def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}", flush=True)

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""
You are an expert SQL code reviewer. Review the provided SQL query against the schema.

Respond with ONLY a valid JSON object — no markdown, no code fences:
{
  "issues": ["issue1", "issue2", ...],
  "severity": "low" | "medium" | "high",
  "fixed_query": "corrected SQL here",
  "explanation": "detailed explanation of all issues"
}

Common issues:
- SELECT * (leaks sensitive columns, over-fetching)
- Unindexed filter/join columns
- Case-sensitive string comparisons on VARCHAR
- Implicit join syntax (comma instead of JOIN keyword)
- GROUP BY on non-unique columns
- Correlated subqueries executed per row (N+1)
- Same subquery computed multiple times (use CTE)
- Wrong join type (INNER when LEFT JOIN needed)
- No status/state filter on transactional tables
- ORDER BY on a derived/computed column (no index possible)
""").strip()


def call_llm(openai_client: OpenAI, sql_query: str, db_schema: str) -> dict:
    user_msg = f"Database Schema:\n{db_schema}\n\nSQL Query:\n{sql_query}\n\nProvide your JSON review."
    try:
        resp = openai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if "```" in raw:
            for part in raw.split("```"):
                part = part.strip().lstrip("json").strip()
                try:
                    return json.loads(part)
                except Exception:
                    continue
        return json.loads(raw)
    except Exception as exc:
        print(f"[DEBUG] LLM error: {exc}", flush=True)
        return {"issues": [], "severity": "low", "fixed_query": None, "explanation": ""}


# ── Single task episode ────────────────────────────────────────────────────────
async def run_task(task_name: str, openai_client: OpenAI) -> float:
    log_start(task=task_name, env=BENCHMARK, model=MODEL_NAME)

    rewards:     List[float] = []
    steps_taken: int         = 0
    score:       float       = 0.0
    success:     bool        = False

    try:
        async with SQLQueryReviewEnv(base_url=f"http://localhost:{PORT}") as env:
            result = await env.reset()
            obs    = result.observation

            for step_num in range(1, MAX_STEPS + 1):
                if result.done:
                    break

                review = call_llm(openai_client, obs.sql_query, obs.db_schema)

                action = SQLReviewAction(
                    issues      = review.get("issues", []),
                    severity    = review.get("severity", "low"),
                    fixed_query = review.get("fixed_query"),
                    explanation = review.get("explanation", ""),
                )

                action_log = f"issues={len(action.issues)},severity={action.severity}"

                result      = await env.step(action)
                reward      = float(result.reward or 0.0)
                done        = result.done
                obs         = result.observation

                rewards.append(reward)
                steps_taken = step_num

                log_step(step=step_num, action=action_log, reward=reward, done=done, error=None)

                if done:
                    break

        score   = min(max(rewards[-1] if rewards else 0.0, 0.0), 1.0)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as exc:
        print(f"[DEBUG] Task error ({task_name}): {exc}", flush=True)

    finally:
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)

    return score


# ── Main — runs all 3 tasks ────────────────────────────────────────────────────
async def main() -> None:
    openai_client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN)
    scores = {}
    for task in ["easy", "medium", "hard"]:
        scores[task] = await run_task(task, openai_client)
        print(f"[DEBUG] task={task} score={scores[task]:.3f}", flush=True)

    avg = sum(scores.values()) / len(scores)
    print(
        f"[DEBUG] average={avg:.3f} easy={scores['easy']:.3f} "
        f"medium={scores['medium']:.3f} hard={scores['hard']:.3f}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())