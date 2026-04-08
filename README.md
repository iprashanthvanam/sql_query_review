---
title: SQL Query Review
emoji: 🔍
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# SQL Query Review Environment

An OpenEnv environment where an AI agent reviews SQL queries for security, performance, and correctness issues — then proposes fixes.

---

## 🎯 Motivation

SQL query review is a real-world task performed by backend engineers and DBAs. This environment helps train AI agents to detect:

- Performance issues (N+1 queries, missing indexes)
- Security flaws (SQL injection risks)
- Logic errors (incorrect joins, aggregations)

---

## 🧠 Tasks

| Task   | Difficulty | Description                            |
| ------ | ---------- | -------------------------------------- |
| easy   | Easy       | SELECT \* with unindexed column        |
| medium | Medium     | Implicit JOIN + GROUP BY bug           |
| hard   | Hard       | N+1 subqueries + duplicate computation |

---

## ⚙️ Action Space

```json
{
  "issues": ["list of issues"],
  "severity": "low | medium | high",
  "fixed_query": "corrected SQL (optional)",
  "explanation": "reasoning"
}
```
