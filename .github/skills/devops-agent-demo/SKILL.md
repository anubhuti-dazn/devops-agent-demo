# DEVOPS-AGENT-DEMO: Root Cause Analysis for FastAPI Task Manager

## When to Use
- Invoked automatically when a CloudWatch alarm fires (application error or CI failure)
- User asks to investigate a broken CI pipeline for the `devops-agent-demo` project
- User wants RCA for a runtime error in the FastAPI Task Manager service

## How Logs Are Provided

**Logs are pre-fetched and passed directly in the prompt — do NOT re-query logs.**

The pipeline (CloudWatch Alarm → SNS → Lambda) already:
1. Queries Coralogix (if configured) or CloudWatch Logs for recent errors
2. Groups errors by subsystem with counts, timestamps, and sample logs
3. For CI failures: fetches the `ci_failure` events from `/devops-agent-demo/ci` log group
4. Passes all data to the agent in the prompt

## Project Overview

**Repository:** `anubhuti-dazn/devops-agent-demo`
**Stack:** Python 3.11 · FastAPI · SQLAlchemy · SQLite · pytest · Docker
**CI:** GitHub Actions — three sequential jobs: `lint → test → build`

### Key Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI app factory, startup, request logging middleware, exception handler |
| `app/config.py` | All env vars: `APP_NAME`, `APP_ENV`, `DATABASE_URL`, `SECRET_KEY`, `MAX_TASKS_PER_USER` |
| `app/models.py` | Pydantic models: `TaskCreate`, `TaskUpdate`, `TaskResponse`, `TaskStatus` enum |
| `app/database.py` | SQLAlchemy engine/session, `TaskDB` ORM model, `get_db()` dependency, `init_db()` |
| `app/routes/tasks.py` | CRUD endpoints: `GET /tasks/`, `POST /tasks/`, `GET/PUT/DELETE /tasks/{id}` |
| `app/routes/health.py` | `GET /health` — runs `SELECT 1` to verify DB connectivity |
| `app/logging_config.py` | JSON formatter + watchtower CloudWatch handler (active when `AWS_REGION` is set) |
| `tests/conftest.py` | `TestClient` fixture with in-memory SQLite, `setup_test_db` autouse fixture |
| `tests/test_tasks.py` | 11 pytest tests covering all CRUD paths + error cases |
| `tests/test_health.py` | 2 tests: root endpoint and health check |
| `.github/workflows/ci.yml` | Three jobs: lint (flake8+ruff), test (pytest+coverage), Docker build+smoke |

### Known Break Scenarios

These scripts are in `scripts/` and are used to deliberately introduce failures for testing:

| Script | What it breaks | Expected CI failure |
|--------|---------------|---------------------|
| `break_01_syntax_error.py` | Removes `)` from `class TaskUpdate(BaseModel):` in `app/models.py` | `SyntaxError` in lint + test |
| `break_02_failing_test.py` | Changes `assert response.status_code == 201` to `200` in `test_create_task` | `AssertionError` in test job |
| `break_03_import_error.py` | Adds `from app.middleware.auth import require_auth` (non-existent) to `app/main.py` | `ModuleNotFoundError` at test collection |
| `break_04_type_error.py` | Changes `/health` to return `"ok"` (string) instead of a dict | `AssertionError` in `test_health_check` |
| `break_05_docker.py` | Adds `RUN apt-get install -y nonexistent-package-xyz-123` to `Dockerfile` | Docker build failure |

To restore: `python scripts/restore_all.py` (runs `git checkout -- app/ tests/ Dockerfile`)

---

## Analysis Workflow

### Step 1: Identify Failure Type

From the prompt, determine:
- Is this a **CI failure** (GitHub Actions pipeline failed)?
- Is this an **application error** (runtime exception in the running service)?

**For CI failures**, the prompt will contain `ci_failure` events with fields:
```json
{
  "level": "ERROR",
  "event": "ci_failure",
  "repo": "anubhuti-dazn/devops-agent-demo",
  "run_id": "...",
  "commit": "...",
  "branch": "...",
  "run_url": "https://github.com/anubhuti-dazn/devops-agent-demo/actions/runs/..."
}
```

**Actions:**
```
Use: repo_read(repository="anubhuti-dazn/devops-agent-demo", hostname="github.com", path=".github/workflows/ci.yml")
# Read the failing workflow to understand the job structure

Use: list_associations  (discover available AWS accounts/tools)
Use: get_datetime       (for analysis_time metadata)
```

---

### Step 2: Fetch CI Logs (CI failures only)

If the prompt contains a `run_url`, use it to identify which job failed.
Then read the relevant source files to find the defect.

**Common failure patterns and where to look:**

| Error type | Job that fails | Files to check |
|-----------|---------------|----------------|
| `SyntaxError` | lint, test | `app/models.py`, `app/routes/*.py`, `app/main.py` |
| `ModuleNotFoundError` | test (collection) | `app/main.py` imports |
| `AssertionError` | test | `tests/test_tasks.py`, `tests/test_health.py` |
| `docker build` failure | build | `Dockerfile` |
| `flake8`/`ruff` violation | lint | Any `app/` or `tests/` file |

**Actions:**
```
Use: repo_read(repository="anubhuti-dazn/devops-agent-demo", hostname="github.com", path="<suspect file>")
Use: repo_grep(repository="anubhuti-dazn/devops-agent-demo", hostname="github.com", pattern="<error pattern>")
```

---

### Step 3: Identify Root Cause

Read the relevant source file. For each failure type:

**SyntaxError:**
- Look for missing `:`, `)`, `(`, unmatched brackets, invalid indentation
- The error message will contain the file and line number

**ModuleNotFoundError:**
- Find the bad import statement in the named file
- Check if the module path exists in the repo

**AssertionError in tests:**
- Read the failing test — what does it assert?
- Read the corresponding route — what does it actually return?
- Identify the mismatch (wrong status code, wrong field name, wrong value)

**Docker build failure:**
- Read the `Dockerfile`
- Identify the failing `RUN` instruction
- Check if it references non-existent packages or files

**Output fields to capture:**
| Field | Required |
|-------|---------|
| `failure_type` | CI or application error | ✅ |
| `failing_job` | lint, test, or build | ✅ |
| `root_cause_file` | File path | ✅ |
| `root_cause_line` | Line number | ✅ |
| `root_cause_code` | The broken code snippet | ✅ |
| `error_message` | Exact error from CI | ✅ |

---

### Step 4: Generate Fix

Provide the exact corrected code.

**For syntax errors:** Show the corrected line.
**For import errors:** Remove or correct the import.
**For test assertion errors:** Correct the assertion to match the actual API contract.
**For Dockerfile errors:** Remove or replace the invalid instruction.

**Output fields to capture:**
| Field | Required |
|-------|---------|
| `fix.file` | File to edit | ✅ |
| `fix.line` | Line to change | ✅ |
| `fix.before` | Current (broken) code | ✅ |
| `fix.after` | Corrected code | ✅ |
| `fix.explanation` | Why this fix works | ✅ |
| `fix.verification` | Command to verify the fix locally | ✅ |

---

### Step 5: Pre-Output Validation

Before generating the final report, verify ALL fields are captured:

```
✅ failure_type
✅ failing_job
✅ root_cause_file
✅ root_cause_line
✅ root_cause_code
✅ error_message
✅ fix.file
✅ fix.line
✅ fix.before
✅ fix.after
✅ fix.explanation
✅ fix.verification
```

If any field is missing, re-read the relevant file before proceeding.

---

### Step 6: Generate Final Report

Output a structured JSON report:

```json
{
  "metadata": {
    "application": "devops-agent-demo",
    "repository": "anubhuti-dazn/devops-agent-demo",
    "analysis_time": "<ISO timestamp>",
    "alarm": "<alarm name>"
  },
  "failure": {
    "type": "ci | application",
    "failing_job": "lint | test | build | runtime",
    "error_message": "<exact error>",
    "root_cause_file": "<path/to/file.py>",
    "root_cause_line": 42,
    "root_cause_code": "<broken code snippet>"
  },
  "fix": {
    "file": "<path/to/file.py>",
    "line": 42,
    "before": "<broken line>",
    "after": "<fixed line>",
    "explanation": "Why this is the fix",
    "verification": "pytest tests/ -v  OR  python -c 'import app.main'"
  },
  "restore_command": "python scripts/restore_all.py",
  "confidence": "high | medium | low"
}
```

---

## Tips

1. **Do NOT re-query logs** — all context is in the prompt
2. **Check the break scripts first** — if a known scenario matches, the fix is known
3. **Read the exact failing file** — do not guess from the error message alone
4. **Provide runnable verification** — always include a command the developer can run locally
5. **If a field cannot be determined**, use `"Unknown - <reason>"` rather than omitting it
