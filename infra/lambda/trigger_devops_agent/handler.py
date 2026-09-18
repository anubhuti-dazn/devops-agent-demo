"""
Lambda entry point.

Flow:
  CloudWatch Alarm → SNS → Lambda → fetch logs (Coralogix or CloudWatch)
                  → build prompt → DevOps Agent (devops-agent boto3 client)
                  → post diagnosis as GitHub issue
"""

import json
import logging
import os
import urllib.request
import urllib.error

import boto3

from agent import run_investigation
from log_fetcher import fetch_app_errors, fetch_ci_failures
from prompt import build_prompt
from config import GITHUB_REPO, GITHUB_TOKEN_SECRET_NAME

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ── GitHub ────────────────────────────────────────────────────────────────────

def _get_github_token() -> str:
    if GITHUB_TOKEN_SECRET_NAME:
        sm = boto3.client("secretsmanager")
        secret = sm.get_secret_value(SecretId=GITHUB_TOKEN_SECRET_NAME)
        return secret.get("SecretString", "")
    return os.environ.get("GITHUB_TOKEN", "")


def _create_github_issue(title: str, body: str) -> str:
    token = _get_github_token()
    if not token or not GITHUB_REPO:
        logger.warning("GitHub issue skipped: GITHUB_REPO or token not configured.")
        return "skipped"

    payload = json.dumps({
        "title": title,
        "body": body,
        "labels": ["devops-agent", "auto-detected"],
    }).encode()

    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            issue = json.loads(resp.read())
            url = issue.get("html_url", "no URL returned")
            logger.info("GitHub issue created: %s", url)
            return url
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        logger.error("GitHub API error %d: %s", e.code, body_text)
        return f"error: {e.code}"


def _build_issue_body(
    alarm_name: str,
    alarm_description: str,
    diagnosis: str,
    token_usage: dict,
    execution_id: str,
) -> str:
    return f"""## Automated Incident Report

**Alarm:** `{alarm_name}`
**Description:** {alarm_description}
**DevOps Agent execution:** `{execution_id}`
**Tokens used:** input={token_usage.get('input_tokens', '?')} output={token_usage.get('output_tokens', '?')}

---

## DevOps Agent Diagnosis

{diagnosis}

---

*Opened automatically by the CloudWatch → SNS → Lambda → DevOps Agent pipeline.*
*Resolve this issue once the fix is merged and verified.*
"""


# ── Lambda handler ────────────────────────────────────────────────────────────

def handler(event, context):
    logger.info(json.dumps({
        "event": "lambda_invoked",
        "records": len(event.get("Records", [])),
    }))

    application_name = os.environ.get("APPLICATION_NAME", "devops-agent-demo")

    for record in event.get("Records", []):
        try:
            _process_record(record, application_name)
        except Exception as exc:
            logger.error("Failed to process record: %s", exc, exc_info=True)

    return {"statusCode": 200, "body": "ok"}


def _process_record(record: dict, application_name: str):
    sns_message = json.loads(record["Sns"]["Message"])
    alarm_name = sns_message.get("AlarmName", "Unknown alarm")
    alarm_description = sns_message.get("AlarmDescription", "")
    new_state = sns_message.get("NewStateValue", "")

    logger.info(json.dumps({
        "event": "alarm_received",
        "alarm": alarm_name,
        "state": new_state,
    }))

    if new_state != "ALARM":
        logger.info("Skipping record: state is %s, not ALARM", new_state)
        return

    # Determine failure type from alarm name
    is_ci_failure = "ci" in alarm_name.lower()

    # Fetch relevant logs
    if is_ci_failure:
        log_samples = fetch_ci_failures(minutes=30)
    else:
        log_samples = fetch_app_errors(application_name)

    logger.info(json.dumps({
        "event": "logs_fetched",
        "alarm": alarm_name,
        "subsystems": len(log_samples),
        "is_ci": is_ci_failure,
    }))

    # Build prompt and run investigation
    investigation_prompt = build_prompt(
        alarm_name=alarm_name,
        alarm_description=alarm_description,
        is_ci_failure=is_ci_failure,
        log_samples=log_samples,
    )

    result = run_investigation(investigation_prompt)

    logger.info(json.dumps({
        "event": "investigation_complete",
        "alarm": alarm_name,
        "execution_id": result.get("execution_id"),
        "token_usage": result.get("token_usage", {}),
    }))

    # Post to GitHub
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    issue_title = f"[Auto] {alarm_name} — {timestamp}"
    issue_body = _build_issue_body(
        alarm_name=alarm_name,
        alarm_description=alarm_description,
        diagnosis=result["content"],
        token_usage=result.get("token_usage", {}),
        execution_id=result.get("execution_id", ""),
    )
    issue_url = _create_github_issue(issue_title, issue_body)

    logger.info(json.dumps({
        "event": "github_issue_created",
        "alarm": alarm_name,
        "issue_url": issue_url,
    }))
