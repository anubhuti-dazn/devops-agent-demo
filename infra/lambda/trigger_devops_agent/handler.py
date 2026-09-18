"""
Lambda handler: receives CloudWatch Alarm via SNS, fetches recent error logs,
calls Amazon Bedrock (Claude) for a diagnosis, then opens a GitHub issue.

Environment variables (set by CDK):
  APP_LOG_GROUP          - CloudWatch log group for app errors
  CI_LOG_GROUP           - CloudWatch log group for CI failures
  BEDROCK_MODEL_ID       - e.g. anthropic.claude-sonnet-4-5
  BEDROCK_REGION         - AWS region where Bedrock is enabled
  GITHUB_REPO            - e.g. anubhuti-dazn/devops-agent-demo
  GITHUB_TOKEN_SECRET_NAME - Secrets Manager secret name holding GitHub PAT (optional)
"""

import json
import os
import urllib.request
import urllib.error
import boto3
from datetime import datetime, timezone, timedelta

logs_client = boto3.client("logs")
bedrock_client = boto3.client("bedrock-runtime", region_name=os.environ.get("BEDROCK_REGION", "eu-west-1"))

BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-5")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")
GITHUB_TOKEN_SECRET_NAME = os.environ.get("GITHUB_TOKEN_SECRET_NAME", "")


# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch_recent_errors(log_group: str, minutes: int = 15) -> list[dict]:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)
    try:
        response = logs_client.filter_log_events(
            logGroupName=log_group,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern='{ $.level = "ERROR" }',
            limit=20,
        )
        events = []
        for e in response.get("events", []):
            try:
                events.append(json.loads(e["message"]))
            except json.JSONDecodeError:
                events.append({"raw": e["message"]})
        return events
    except Exception as exc:
        return [{"error": f"Could not fetch logs: {exc}"}]


def fetch_ci_failure_context(log_group: str, minutes: int = 30) -> list[dict]:
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)
    try:
        response = logs_client.filter_log_events(
            logGroupName=log_group,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern='{ $.event = "ci_failure" }',
            limit=5,
        )
        events = []
        for e in response.get("events", []):
            try:
                events.append(json.loads(e["message"]))
            except json.JSONDecodeError:
                events.append({"raw": e["message"]})
        return events
    except Exception as exc:
        return [{"error": f"Could not fetch CI logs: {exc}"}]


def call_bedrock(alarm_name: str, error_logs: list, ci_events: list) -> str:
    log_text = json.dumps(error_logs, indent=2) if error_logs else "No error logs found."
    ci_text = json.dumps(ci_events, indent=2) if ci_events else "No CI failure events found."

    prompt = f"""You are a DevOps agent investigating a production incident.

## Alarm triggered
{alarm_name}

## Recent application error logs (last 15 min)
{log_text}

## Recent CI failure events (last 30 min)
{ci_text}

## Your task
1. Identify the root cause of the failure in one sentence.
2. List the exact file(s) and line(s) that need to be changed.
3. Show the fix as a code diff or the corrected lines.
4. Describe a test to verify the fix works.

Be concise and actionable. Focus on what a developer should do right now."""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        response = bedrock_client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    except Exception as exc:
        return f"Bedrock call failed: {exc}\n\nRaw error logs:\n{log_text}"


def get_github_token() -> str:
    if not GITHUB_TOKEN_SECRET_NAME:
        return os.environ.get("GITHUB_TOKEN", "")
    sm = boto3.client("secretsmanager")
    secret = sm.get_secret_value(SecretId=GITHUB_TOKEN_SECRET_NAME)
    return secret.get("SecretString", "")


def create_github_issue(title: str, body: str) -> str:
    token = get_github_token()
    if not token or not GITHUB_REPO:
        return "GitHub issue skipped: no token or repo configured."

    payload = json.dumps({"title": title, "body": body, "labels": ["devops-agent", "auto-detected"]}).encode()
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
            return issue.get("html_url", "Issue created (no URL returned)")
    except urllib.error.HTTPError as e:
        return f"GitHub API error {e.code}: {e.read().decode()}"


# ── Entry point ───────────────────────────────────────────────────────────────

def handler(event, context):
    print(json.dumps({"event": "lambda_invoked", "records": len(event.get("Records", []))}))

    app_log_group = os.environ.get("APP_LOG_GROUP", "/devops-agent-demo/production")
    ci_log_group = os.environ.get("CI_LOG_GROUP", "/devops-agent-demo/ci")

    for record in event.get("Records", []):
        sns_message = json.loads(record["Sns"]["Message"])
        alarm_name = sns_message.get("AlarmName", "Unknown alarm")
        new_state = sns_message.get("NewStateValue", "")
        alarm_desc = sns_message.get("AlarmDescription", "")

        print(json.dumps({"event": "alarm_received", "alarm": alarm_name, "state": new_state}))

        if new_state != "ALARM":
            print(json.dumps({"event": "alarm_skipped", "reason": f"state is {new_state}, not ALARM"}))
            continue

        # Fetch context
        is_ci_alarm = "ci" in alarm_name.lower()
        app_errors = [] if is_ci_alarm else fetch_recent_errors(app_log_group)
        ci_events = fetch_ci_failure_context(ci_log_group)

        # Diagnose with Bedrock
        diagnosis = call_bedrock(alarm_name, app_errors, ci_events)
        print(json.dumps({"event": "diagnosis_generated", "alarm": alarm_name}))

        # Build GitHub issue body
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        issue_body = f"""## Automated incident report — {timestamp}

**Alarm:** `{alarm_name}`
**Description:** {alarm_desc}

---

## DevOps Agent Diagnosis

{diagnosis}

---

*This issue was opened automatically by the CloudWatch → Lambda → Bedrock pipeline.*
*To suppress false positives, resolve this issue once the fix is merged.*
"""

        issue_title = f"[Auto] {alarm_name} — {timestamp}"
        issue_url = create_github_issue(issue_title, issue_body)

        print(json.dumps({
            "event": "github_issue_created",
            "alarm": alarm_name,
            "issue_url": issue_url,
        }))

    return {"statusCode": 200, "body": "ok"}
