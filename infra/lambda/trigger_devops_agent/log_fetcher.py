"""
Log fetcher with Coralogix primary and CloudWatch fallback.

If CORALOGIX_ENDPOINT + CORALOGIX_API_KEY are set  → queries Coralogix using
the same Elasticsearch DSL pattern as rca-analyser.
Otherwise                                           → falls back to CloudWatch
Logs filter_log_events on the configured log groups.
"""

import logging
import json
from datetime import datetime, timedelta, timezone

from config import (
    CORALOGIX_API_KEY,
    CORALOGIX_ENDPOINT,
    QUERY_WINDOW_HOURS,
    APP_LOG_GROUP,
    CI_LOG_GROUP,
    logs_client,
)

logger = logging.getLogger(__name__)

_coralogix_available = bool(CORALOGIX_ENDPOINT and CORALOGIX_API_KEY)


# ── Coralogix ─────────────────────────────────────────────────────────────────

def _query_coralogix(application_name: str) -> list[dict]:
    """
    Query Coralogix for recent errors grouped by subsystem.
    Returns a list of subsystem dicts, each matching the rca-analyser log_samples schema:
      { name, error_count, first_seen, last_seen, sample_logs }
    """
    import httpx  # only imported when Coralogix is configured

    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(hours=QUERY_WINDOW_HOURS)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    cx_query = {
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"coralogix.metadata.applicationName": application_name}},
                    {"range": {"coralogix.metadata.severity": {"gte": 5}}},
                    {
                        "range": {
                            "coralogix.timestamp": {
                                "gte": start_ms,
                                "lt": end_ms,
                                "format": "epoch_millis",
                            }
                        }
                    },
                ]
            }
        },
        "aggs": {
            "by_subsystem": {
                "terms": {
                    "field": "coralogix.metadata.subsystemName",
                    "size": 50,
                    "order": {"_count": "desc"},
                },
                "aggs": {
                    "sample_logs": {
                        "top_hits": {
                            "size": 3,
                            "sort": [{"coralogix.timestamp": {"order": "desc"}}],
                        }
                    },
                    "first_seen": {"min": {"field": "coralogix.timestamp"}},
                    "last_seen": {"max": {"field": "coralogix.timestamp"}},
                },
            }
        },
    }

    logger.info("Querying Coralogix for app=%s window=%dh", application_name, QUERY_WINDOW_HOURS)
    resp = httpx.post(
        CORALOGIX_ENDPOINT,
        headers={
            "Authorization": f"Bearer {CORALOGIX_API_KEY}",
            "Content-Type": "application/json",
        },
        json=cx_query,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    subsystems = []
    for bucket in data.get("aggregations", {}).get("by_subsystem", {}).get("buckets", []):
        first_ms = bucket.get("first_seen", {}).get("value")
        last_ms = bucket.get("last_seen", {}).get("value")
        subsystems.append({
            "source": "coralogix",
            "name": bucket["key"],
            "error_count": bucket["doc_count"],
            "first_seen": datetime.fromtimestamp(first_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if first_ms else None,
            "last_seen": datetime.fromtimestamp(last_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if last_ms else None,
            "sample_logs": [h.get("_source", {}) for h in bucket.get("sample_logs", {}).get("hits", {}).get("hits", [])],
        })

    logger.info("Coralogix returned %d subsystems for app=%s", len(subsystems), application_name)
    return subsystems


# ── CloudWatch fallback ───────────────────────────────────────────────────────

def _query_cloudwatch(log_group: str, filter_pattern: str, minutes: int) -> list[dict]:
    """
    Filter CloudWatch Logs for recent events matching the pattern.
    Returns a flat list of parsed log dicts.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)

    try:
        response = logs_client.filter_log_events(
            logGroupName=log_group,
            startTime=int(start.timestamp() * 1000),
            endTime=int(end.timestamp() * 1000),
            filterPattern=filter_pattern,
            limit=20,
        )
    except Exception as exc:
        logger.warning("CloudWatch filter_log_events failed for %s: %s", log_group, exc)
        return []

    events = []
    for e in response.get("events", []):
        try:
            events.append(json.loads(e["message"]))
        except json.JSONDecodeError:
            events.append({"raw": e["message"], "timestamp": e.get("timestamp")})

    logger.info("CloudWatch returned %d events from %s", len(events), log_group)
    return events


def _cloudwatch_as_subsystems(events: list[dict], subsystem_name: str) -> list[dict]:
    """Wrap flat CloudWatch events into the rca-analyser log_samples subsystem schema."""
    if not events:
        return []
    return [{
        "source": "cloudwatch",
        "name": subsystem_name,
        "error_count": len(events),
        "first_seen": None,
        "last_seen": None,
        "sample_logs": events,
    }]


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_app_errors(application_name: str) -> list[dict]:
    """
    Fetch application errors.
    Uses Coralogix if configured, otherwise CloudWatch.
    Returns list of subsystem dicts (log_samples schema).
    """
    if _coralogix_available:
        try:
            return _query_coralogix(application_name)
        except Exception as exc:
            logger.warning("Coralogix query failed, falling back to CloudWatch: %s", exc)

    events = _query_cloudwatch(APP_LOG_GROUP, '{ $.level = "ERROR" }', QUERY_WINDOW_HOURS * 60)
    return _cloudwatch_as_subsystems(events, "app")


def fetch_ci_failures(minutes: int = 30) -> list[dict]:
    """
    Fetch CI failure events from CloudWatch (always uses CloudWatch — CI logs come from GitHub Actions).
    Returns list of subsystem dicts.
    """
    events = _query_cloudwatch(CI_LOG_GROUP, '{ $.event = "ci_failure" }', minutes)
    return _cloudwatch_as_subsystems(events, "ci-pipeline")
