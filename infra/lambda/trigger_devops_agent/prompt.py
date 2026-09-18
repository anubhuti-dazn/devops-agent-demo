"""
Build the investigation prompt for the DevOps Agent.

The prompt tells the agent which skill to use and provides pre-fetched log data
so the agent does not need to re-query logs itself — matching the rca-analyser pattern.
"""

import json
from datetime import datetime, timezone

GITHUB_REPO = "anubhuti-dazn/devops-agent-demo"
MAX_PROMPT_BYTES = 30_000  # stay within the agent's ~32KB prompt limit


def build_prompt(
    alarm_name: str,
    alarm_description: str,
    is_ci_failure: bool,
    log_samples: list[dict],
) -> str:
    """
    Build the investigation prompt.

    Args:
        alarm_name: CloudWatch alarm name that fired.
        alarm_description: Alarm description string.
        is_ci_failure: True if this was triggered by a CI pipeline failure alarm.
        log_samples: List of subsystem dicts in the rca-analyser log_samples schema.

    Returns:
        Prompt string ready to send to the DevOps Agent.
    """
    analysis_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_source = "CloudWatch" if not log_samples or log_samples[0].get("source") == "cloudwatch" else "Coralogix"

    if is_ci_failure:
        failure_context = _build_ci_context(log_samples)
        prompt = f"""Under custom skills use the skill devops-agent-demo to perform a CI failure root cause analysis.

## Incident Details
- **Alarm**: {alarm_name}
- **Description**: {alarm_description}
- **Analysis time**: {analysis_time}
- **Failure type**: CI Pipeline Failure
- **GitHub repository**: {GITHUB_REPO}
- **Log source**: {log_source}

## CI Failure Context (pre-fetched — do NOT re-query logs)

{failure_context}

## Project Structure (for reference)
```
devops-agent-demo/
├── app/
│   ├── main.py          # FastAPI entry point + middleware
│   ├── config.py        # Env var configuration
│   ├── models.py        # Pydantic models (TaskCreate, TaskUpdate, TaskResponse)
│   ├── database.py      # SQLAlchemy + SQLite (TaskDB model, get_db, init_db)
│   └── routes/
│       ├── tasks.py     # CRUD: GET/POST/PUT/DELETE /tasks/{{id}}
│       └── health.py    # GET /health (database connectivity check)
├── tests/
│   ├── conftest.py      # TestClient + in-memory SQLite fixture
│   ├── test_tasks.py    # 11 tests covering all task CRUD paths
│   └── test_health.py   # 2 tests for root + health endpoints
├── .github/workflows/
│   └── ci.yml           # lint (flake8+ruff) → test (pytest+coverage) → docker build
├── Dockerfile
└── scripts/
    ├── break_01_syntax_error.py   # Introduces SyntaxError in app/models.py
    ├── break_02_failing_test.py   # Wrong assertion in tests/test_tasks.py
    ├── break_03_import_error.py   # Bad import in app/main.py
    ├── break_04_type_error.py     # /health returns string instead of dict
    ├── break_05_docker.py         # Invalid apt-get in Dockerfile
    └── restore_all.py             # git checkout -- app/ tests/ Dockerfile
```

Investigate the CI failure, identify the exact file and line causing it, and provide a fix.
"""
    else:
        log_context = _build_app_log_context(log_samples)
        prompt = f"""Under custom skills use the skill devops-agent-demo to perform a root cause analysis.

## Incident Details
- **Alarm**: {alarm_name}
- **Description**: {alarm_description}
- **Analysis time**: {analysis_time}
- **Failure type**: Application Error
- **GitHub repository**: {GITHUB_REPO}
- **Log source**: {log_source}

## Application Error Logs (pre-fetched — do NOT re-query logs)

{log_context}

## Application Context
- **Service**: FastAPI Task Manager (Python 3.11, SQLAlchemy, SQLite)
- **Endpoints**: GET/POST/PUT/DELETE /tasks, GET /health, GET /
- **Deployment**: Docker container, exposed on port 8000
- **Key files**: app/main.py, app/routes/tasks.py, app/routes/health.py, app/models.py, app/database.py

Investigate the application error, identify the root cause (code, configuration, or infrastructure),
and provide a specific fix with the exact file paths and lines to change.
"""

    # Truncate if over the limit
    encoded = prompt.encode("utf-8")
    if len(encoded) > MAX_PROMPT_BYTES:
        prompt = encoded[:MAX_PROMPT_BYTES].decode("utf-8", errors="ignore")
        prompt += "\n\n[prompt truncated to stay within size limit]"

    return prompt


def _build_ci_context(log_samples: list[dict]) -> str:
    if not log_samples:
        return "No CI failure events captured."

    lines = []
    for subsystem in log_samples:
        for entry in subsystem.get("sample_logs", []):
            lines.append(json.dumps(entry, indent=2))

    return "\n\n".join(lines) if lines else "No CI failure events captured."


def _build_app_log_context(log_samples: list[dict]) -> str:
    if not log_samples:
        return "No error logs captured."

    sections = []
    for subsystem in log_samples:
        header = (
            f"### Subsystem: {subsystem.get('name', 'unknown')}\n"
            f"- Error count: {subsystem.get('error_count', '?')}\n"
            f"- First seen: {subsystem.get('first_seen', 'unknown')}\n"
            f"- Last seen: {subsystem.get('last_seen', 'unknown')}\n"
        )
        samples = subsystem.get("sample_logs", [])
        sample_text = "\n".join(json.dumps(s, indent=2) for s in samples[:3])
        sections.append(header + "\n**Sample logs:**\n```json\n" + sample_text + "\n```")

    return "\n\n".join(sections)
