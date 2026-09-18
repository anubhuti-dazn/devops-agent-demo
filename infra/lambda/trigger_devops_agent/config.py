"""
Environment variables and boto3 clients.
Matches the config.py pattern used in rca-analyser.
"""

import os
import boto3

# ── DevOps Agent ──────────────────────────────────────────────────────────────
AGENT_SPACE_ID = os.environ.get("AGENT_SPACE_ID", "")
REGION = os.environ.get("AWS_REGION", "eu-central-1")

# ── Coralogix (optional — falls back to CloudWatch if not set) ────────────────
CORALOGIX_API_KEY = os.environ.get("CORALOGIX_API_KEY", "")
CORALOGIX_ENDPOINT = os.environ.get("CORALOGIX_ENDPOINT", "")
QUERY_WINDOW_HOURS = int(os.environ.get("QUERY_WINDOW_HOURS", "1"))

# ── CloudWatch fallback ───────────────────────────────────────────────────────
APP_LOG_GROUP = os.environ.get("APP_LOG_GROUP", "/devops-agent-demo/production")
CI_LOG_GROUP = os.environ.get("CI_LOG_GROUP", "/devops-agent-demo/ci")

# ── GitHub issue reporting ────────────────────────────────────────────────────
GITHUB_REPO = os.environ.get("GITHUB_REPO", "anubhuti-dazn/devops-agent-demo")
GITHUB_TOKEN_SECRET_NAME = os.environ.get("GITHUB_TOKEN_SECRET_NAME", "")

# ── Boto3 clients — reused across warm Lambda invocations ─────────────────────
devops_client = boto3.client("devops-agent", region_name=REGION)
logs_client = boto3.client("logs", region_name=REGION)
