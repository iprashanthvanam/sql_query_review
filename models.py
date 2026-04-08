
"""
SQL Query Review Environment — Models
Pure Pydantic models compatible with OpenEnv spec.
Uses 'db_schema' consistently (not 'schema' which conflicts with Pydantic).
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class SQLReviewAction(BaseModel):
    """Agent's SQL review submission."""
    issues: List[str] = Field(default_factory=list,
        description="List of issues found, e.g. ['SELECT *', 'missing index']")
    severity: str = Field(default="low",
        description="Overall severity: low | medium | high")
    fixed_query: Optional[str] = Field(default=None,
        description="Agent's corrected SQL query")
    explanation: str = Field(default="",
        description="Free-text explanation of issues found")


class SQLReviewObservation(BaseModel):
    """What the agent sees each step."""
    feedback: str = Field(default="",
        description="Grader feedback (empty on reset)")
    task_name: str = Field(default="",
        description="easy | medium | hard")
    sql_query: str = Field(default="",
        description="The SQL query to review")
    db_schema: str = Field(default="",
        description="Database schema context")
    issues_found: int = Field(default=0,
        description="Number of valid issues matched so far")
    step: int = Field(default=0)
    done: bool = Field(default=False)
    reward: float = Field(default=0.0,
        description="Reward in [0.0, 1.0]")


class SQLReviewState(BaseModel):
    """Full internal episode state."""
    episode_id: str = ""
    task_name: str = ""
    sql_query: str = ""
    db_schema: str = ""
    expected_issues: List[str] = Field(default_factory=list)
    expected_severity: str = "low"
    correct_fixed_query: Optional[str] = None
    step_count: int = 0
    total_reward: float = 0.0
    issues_found: int = 0