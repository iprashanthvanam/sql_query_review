

"""
SQL Query Review Environment — HTTP Client
Works with the standalone FastAPI server (app.py).
"""
import asyncio
import json
from typing import Optional, List
import httpx

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import SQLReviewAction, SQLReviewObservation, SQLReviewState


class StepResult:
    def __init__(self, observation: SQLReviewObservation, reward: float, done: bool):
        self.observation = observation
        self.reward = reward
        self.done = done


class SQLQueryReviewEnv:
    """
    Async HTTP client for the SQL Query Review environment.

    Usage:
        async with SQLQueryReviewEnv(base_url="http://localhost:7860") as env:
            result = await env.reset()
            obs = result.observation
            result = await env.step(SQLReviewAction(
                issues=["select star", "no index"],
                severity="medium",
                fixed_query="SELECT id, name FROM users WHERE LOWER(name)='admin';",
                explanation="SELECT * leaks password_hash and name is unindexed.",
            ))
            print(result.observation.feedback)
    """

    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def _parse_obs(self, data: dict) -> SQLReviewObservation:
        obs_data = data.get("observation", data)
        return SQLReviewObservation(
            feedback=obs_data.get("feedback", ""),
            task_name=obs_data.get("task_name", ""),
            sql_query=obs_data.get("sql_query", ""),
            db_schema=obs_data.get("db_schema", ""),
            issues_found=obs_data.get("issues_found", 0),
            step=obs_data.get("step", 0),
            done=obs_data.get("done", False),
            reward=obs_data.get("reward", 0.0),
        )

    async def reset(self) -> StepResult:
        assert self._client, "Use 'async with SQLQueryReviewEnv(...) as env:'"
        resp = await self._client.post("/reset", json={})
        resp.raise_for_status()
        data = resp.json()
        obs = self._parse_obs(data)
        return StepResult(observation=obs, reward=0.0, done=False)

    async def step(self, action: SQLReviewAction) -> StepResult:
        assert self._client, "Use 'async with SQLQueryReviewEnv(...) as env:'"
        payload = {
            "action": {
                "issues": action.issues,
                "severity": action.severity,
                "fixed_query": action.fixed_query,
                "explanation": action.explanation,
            },
            "timeout_s": 30,
        }
        resp = await self._client.post("/step", json=payload)
        resp.raise_for_status()
        data = resp.json()
        obs = self._parse_obs(data)
        return StepResult(
            observation=obs,
            reward=data.get("reward", obs.reward),
            done=data.get("done", obs.done),
        )

    async def get_state(self) -> SQLReviewState:
        assert self._client
        resp = await self._client.get("/state")
        resp.raise_for_status()
        data = resp.json()
        return SQLReviewState(**data)

    async def close(self):
        if self._client:
            await self._client.aclose()