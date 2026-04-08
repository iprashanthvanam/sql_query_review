---
title: SQL Query Review
emoji: 🔍
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
tags:
  - openenv
  - sql
  - code-review
  - real-world
---

# SQL Query Review Environment

An OpenEnv environment where an AI agent reviews SQL queries for security, performance, and correctness issues — then proposes fixes.

---

## 🎯 Motivation

SQL query review is a real-world task performed daily by DBAs, backend engineers, and data teams. Automating it with RL-trained agents has direct production value: catching N+1 queries, SQL injection risks, and missing indexes before they reach production.

- **Performance issues** — N+1 queries, missing indexes
- **Security flaws** — SQL injection risks
- **Logic errors** — incorrect joins, aggregations, GROUP BY bugs

---

## 🧠 Tasks

| Task     | Difficulty | Description                                                                 |
| -------- | ---------- | --------------------------------------------------------------------------- |
| `easy`   | Easy       | `SELECT *` with loose string match on unindexed column                      |
| `medium` | Medium     | Implicit JOIN with `GROUP BY` on non-unique column                          |
| `hard`   | Hard       | N+1 correlated subqueries with duplicated computation and status filter bug |

---

## ⚙️ Action Space

`SQLReviewAction` — the agent's review submission:

| Field         | Type            | Description                                           |
| ------------- | --------------- | ----------------------------------------------------- |
| `issues`      | `List[str]`     | Issues found, e.g. `["SELECT *", "no index on name"]` |
| `severity`    | `str`           | `"low"` \| `"medium"` \| `"high"`                     |
| `fixed_query` | `Optional[str]` | Agent's corrected SQL                                 |
| `explanation` | `str`           | Free-text explanation                                 |

```json
{
  "issues": ["list of issue strings found"],
  "severity": "low | medium | high",
  "fixed_query": "corrected SQL (optional)",
  "explanation": "reasoning"
}
```

---

## 👁️ Observation Space

`SQLReviewObservation` — what the agent sees:

| Field          | Type    | Description                        |
| -------------- | ------- | ---------------------------------- |
| `task_name`    | `str`   | `"easy"` \| `"medium"` \| `"hard"` |
| `sql_query`    | `str`   | The SQL query to review            |
| `db_schema`    | `str`   | Database schema context            |
| `feedback`     | `str`   | Grader feedback after each step    |
| `issues_found` | `int`   | How many valid issues matched      |
| `step`         | `int`   | Current step                       |
| `done`         | `bool`  | Episode complete                   |
| `reward`       | `float` | Reward in [0.0, 1.0]               |

```json
{
  "task_name": "easy | medium | hard",
  "sql_query": "the SQL to review",
  "db_schema": "table definitions",
  "feedback": "grader feedback string",
  "issues_found": 2,
  "step": 1,
  "done": true,
  "reward": 0.833
}
```

---

## 🏆 Reward Function

| Component            | Max     | Criteria                                        |
| -------------------- | ------- | ----------------------------------------------- |
| Issue identification | 0.5     | Proportional to issues correctly identified     |
| Severity assessment  | 0.2     | Exact=0.2, one level off=0.1, wrong=0.0         |
| Fixed query quality  | 0.2     | Structural keyword matching against correct fix |
| Explanation depth    | 0.1     | Length-based — >30 chars = 0.1                  |
| **Total**            | **1.0** |                                                 |

---

## 🚀 Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app:app --host 0.0.0.0 --port 7860 --reload

# Or with Docker
docker build -t sql-query-review:latest -f server/Dockerfile .
docker run -d -p 7860:7860 -e SQL_REVIEW_TASK=easy sql-query-review:latest
```

---

## 🔌 API Endpoints

| Endpoint    | Method    | Description                     |
| ----------- | --------- | ------------------------------- |
| `/health`   | GET       | Health check                    |
| `/reset`    | POST      | Start new episode               |
| `/step`     | POST      | Submit review action            |
| `/state`    | GET       | Current episode state           |
| `/schema`   | GET       | Action/Observation JSON schemas |
| `/metadata` | GET       | Environment metadata            |
| `/docs`     | GET       | Swagger UI                      |
| `/ws`       | WebSocket | Persistent session              |

### Example API Usage

```bash
# Health check
curl http://localhost:7860/health

# Reset environment
curl -X POST http://localhost:7860/reset \
  -H "Content-Type: application/json" -d '{}'

# Submit a review
curl -X POST http://localhost:7860/step \
  -H "Content-Type: application/json" \
  -d '{
    "action": {
      "issues": ["select star", "no index"],
      "severity": "medium",
      "fixed_query": "SELECT id, name FROM users WHERE LOWER(name) = '\''admin'\'';",
      "explanation": "SELECT * leaks sensitive columns; name match should use LOWER for case-insensitive comparison."
    }
  }'
```

---

## 🤖 Run Inference

```bash
export HF_TOKEN=hf_your_token_here
export API_BASE_URL=https://router.huggingface.co/v1
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
export ENV_BASE_URL=https://YOUR_USERNAME-sql-query-review.hf.space
python inference.py
```

---

## 📊 Baseline Scores

| Task   | Model                | Score |
| ------ | -------------------- | ----- |
| easy   | Qwen2.5-72B-Instruct | ~0.75 |
| medium | Qwen2.5-72B-Instruct | ~0.55 |
| hard   | Qwen2.5-72B-Instruct | ~0.40 |

---

## 🚢 Deploy to Hugging Face Spaces

```bash
# From the environment directory
openenv push

# Or with options
openenv push --repo-id my-org/my-env --private
```

The deployed space includes:

- **Web Interface** at `/web` — Interactive UI for exploring the environment
- **API Documentation** at `/docs` — Full OpenAPI/Swagger interface
- **Health Check** at `/health` — Container health monitoring
- **WebSocket** at `/ws` — Persistent session endpoint for low-latency interactions

---

## 📁 Project Structure

```
sql_query_review/
├── .dockerignore
├── __init__.py
├── README.md
├── openenv.yaml
├── pyproject.toml
├── uv.lock
├── client.py
├── models.py
├── inference.py
└── server/
    ├── __init__.py
    ├── sql_query_review_environment.py
    ├── app.py
    └── Dockerfile
```
