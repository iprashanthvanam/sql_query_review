

"""
SQL Query Review Environment — Core Logic
3 tasks: easy → medium → hard, each with a deterministic grader (0.0–1.0).
Standalone — no openenv.core dependency in this file.
"""
import os
import sys
import uuid
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import SQLReviewAction, SQLReviewObservation, SQLReviewState

# ── Task definitions ──────────────────────────────────────────────────────────

TASKS = {
    "easy": {
        "sql_query": "SELECT * FROM users WHERE name = 'admin';",
        "schema": (
            "Table: users(id INT PK, name VARCHAR, email VARCHAR, "
            "password_hash VARCHAR, role VARCHAR)\n"
            "Table: orders(id INT PK, user_id INT FK users.id, "
            "total DECIMAL, created_at TIMESTAMP)"
        ),
        "expected_issues": ["select star", "no index", "case sensitive"],
        "expected_severity": "medium",
        "correct_fixed_query": (
            "SELECT id, name, email, role FROM users WHERE LOWER(name) = 'admin';"
        ),
    },
    "medium": {
        "sql_query": (
            "SELECT u.name, COUNT(o.id) as order_count\n"
            "FROM users u, orders o\n"
            "WHERE u.id = o.user_id\n"
            "GROUP BY u.name;"
        ),
        "schema": (
            "Table: users(id INT PK, name VARCHAR, email VARCHAR)\n"
            "Table: orders(id INT PK, user_id INT FK users.id, "
            "total DECIMAL, status VARCHAR, created_at TIMESTAMP)"
        ),
        "expected_issues": [
            "implicit join", "group by name", "missing index", "excludes null"
        ],
        "expected_severity": "high",
        "correct_fixed_query": (
            "SELECT u.id, u.name, COUNT(o.id) AS order_count\n"
            "FROM users u\n"
            "LEFT JOIN orders o ON u.id = o.user_id\n"
            "GROUP BY u.id, u.name;"
        ),
    },
    "hard": {
        "sql_query": (
            "SELECT p.name, p.price,\n"
            "       (SELECT AVG(price) FROM products) as avg_price,\n"
            "       (SELECT COUNT(*) FROM order_items oi "
            "WHERE oi.product_id = p.id) as sold\n"
            "FROM products p\n"
            "WHERE p.price > (SELECT AVG(price) FROM products)\n"
            "ORDER BY sold DESC\n"
            "LIMIT 10;"
        ),
        "schema": (
            "Table: products(id INT PK, name VARCHAR, price DECIMAL, "
            "category_id INT, stock INT)\n"
            "Table: order_items(id INT PK, order_id INT, "
            "product_id INT FK products.id, qty INT, unit_price DECIMAL)\n"
            "Table: orders(id INT PK, user_id INT, status VARCHAR, created_at TIMESTAMP)"
        ),
        "expected_issues": [
            "correlated subquery",
            "duplicate subquery",
            "no covering index",
            "sort on derived column",
            "missing filter on status",
        ],
        "expected_severity": "high",
        "correct_fixed_query": (
            "WITH avg_price AS (SELECT AVG(price) AS val FROM products),\n"
            "     sold_counts AS (\n"
            "         SELECT oi.product_id, COUNT(*) AS sold\n"
            "         FROM order_items oi\n"
            "         JOIN orders o ON oi.order_id = o.id\n"
            "         WHERE o.status = 'completed'\n"
            "         GROUP BY oi.product_id\n"
            "     )\n"
            "SELECT p.name, p.price, a.val AS avg_price, COALESCE(s.sold, 0) AS sold\n"
            "FROM products p\n"
            "CROSS JOIN avg_price a\n"
            "LEFT JOIN sold_counts s ON s.product_id = p.id\n"
            "WHERE p.price > a.val\n"
            "ORDER BY sold DESC\n"
            "LIMIT 10;"
        ),
    },
}

# ── Grading helpers ───────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return text.lower().strip()


def _count_matching_issues(found: list, expected: list) -> int:
    """Fuzzy keyword match — counts how many expected issues the agent found."""
    matched = 0
    for exp in expected:
        exp_words = set(_normalize(exp).split())
        for found_issue in found:
            found_words = set(_normalize(found_issue).split())
            if exp_words & found_words:
                matched += 1
                break
    return matched


def _score_fixed_query(proposed: Optional[str], correct: Optional[str]) -> float:
    """Partial credit for fixed query based on structural keywords."""
    if not proposed or not correct:
        return 0.0
    p = _normalize(proposed)
    c = _normalize(correct)
    key_terms = ["join", "where", "group by", "with", "left join", "coalesce", "cte"]
    correct_terms = [t for t in key_terms if t in c]
    if not correct_terms:
        return 0.5 if len(p) > 20 else 0.0
    matched = sum(1 for t in correct_terms if t in p)
    return round(matched / len(correct_terms), 2)


# ── Environment class ─────────────────────────────────────────────────────────

class SQLQueryReviewEnvironment:
    """
    SQL Query Review Environment.

    Reward breakdown per episode (total max = 1.0):
      - Issue identification : 0.0–0.5  (proportional to issues found)
      - Severity correctness : 0.0–0.2  (exact=0.2, one-off=0.1)
      - Fixed query quality  : 0.0–0.2  (structural keyword match)
      - Explanation depth    : 0.0–0.1  (length-based)
    """

    def __init__(self, task_name: str = "easy"):
        self._task_name = task_name if task_name in TASKS else "easy"
        self._state = self._make_state()

    def _make_state(self) -> SQLReviewState:
        task = TASKS[self._task_name]
        return SQLReviewState(
            episode_id=str(uuid.uuid4()),
            task_name=self._task_name,
            sql_query=task["sql_query"],
            db_schema=task["schema"],
            expected_issues=task["expected_issues"],
            expected_severity=task["expected_severity"],
            correct_fixed_query=task.get("correct_fixed_query"),
            step_count=0,
            total_reward=0.0,
            issues_found=0,
        )

    def reset(self, **kwargs) -> SQLReviewObservation:
        self._state = self._make_state()
        task = TASKS[self._task_name]
        return SQLReviewObservation(
            feedback="",
            task_name=self._task_name,
            sql_query=task["sql_query"],
            db_schema=task["schema"],
            issues_found=0,
            step=0,
            done=False,
            reward=0.0,
        )

    def step(self, action: SQLReviewAction, **kwargs) -> SQLReviewObservation:
        s = self._state
        task = TASKS[s.task_name]
        s.step_count += 1

        # Grade issues (0.0–0.5)
        matched = _count_matching_issues(action.issues, task["expected_issues"])
        total_expected = len(task["expected_issues"])
        issue_score = round((matched / total_expected) * 0.5, 3) if total_expected else 0.0
        s.issues_found = matched

        # Grade severity (0.0–0.2)
        levels = ["low", "medium", "high"]
        try:
            diff = abs(levels.index(action.severity) - levels.index(task["expected_severity"]))
            severity_score = 0.2 if diff == 0 else (0.1 if diff == 1 else 0.0)
        except ValueError:
            severity_score = 0.0

        # Grade fixed query (0.0–0.2)
        fix_score = _score_fixed_query(action.fixed_query, task.get("correct_fixed_query")) * 0.2

        # Grade explanation (0.0–0.1)
        expl_len = len(action.explanation.strip())
        explanation_score = 0.1 if expl_len > 30 else (0.05 if expl_len > 10 else 0.0)

        reward = round(
            min(max(issue_score + severity_score + fix_score + explanation_score, 0.0), 1.0), 3
        )
        s.total_reward = reward

        feedback = " | ".join([
            f"Issues matched: {matched}/{total_expected} ({issue_score:.2f} pts)",
            f"Severity: {'correct' if severity_score==0.2 else 'partial' if severity_score==0.1 else 'wrong'} ({severity_score:.2f} pts)",
            f"Fix: {fix_score:.2f} pts",
            f"Explanation: {explanation_score:.2f} pts",
            f"Total: {reward:.3f}",
        ])

        return SQLReviewObservation(
            feedback=feedback,
            task_name=s.task_name,
            sql_query=task["sql_query"],
            db_schema=task["schema"],
            issues_found=matched,
            step=s.step_count,
            done=True,
            reward=reward,
        )

    @property
    def state(self) -> SQLReviewState:
        return self._state