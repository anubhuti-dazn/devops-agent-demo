import logging
import json
import os
from datetime import datetime, timezone

AWS_REGION = os.getenv("AWS_REGION", "")
LOG_GROUP = os.getenv("CW_LOG_GROUP", "/devops-agent-demo")
APP_ENV = os.getenv("APP_ENV", "development")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "env": APP_ENV,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        return json.dumps(log_entry)


def setup_logging() -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(JSONFormatter())
    root.addHandler(console)

    if AWS_REGION:
        try:
            import watchtower
            import boto3

            client = boto3.client("logs", region_name=AWS_REGION)
            cw_handler = watchtower.CloudWatchLogHandler(
                boto3_client=client,
                log_group_name=f"{LOG_GROUP}/{APP_ENV}",
                log_stream_name=f"app-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            )
            cw_handler.setFormatter(JSONFormatter())
            root.addHandler(cw_handler)
            root.info("CloudWatch logging enabled", extra={"extra": {"log_group": f"{LOG_GROUP}/{APP_ENV}"}})
        except Exception as e:
            root.warning(f"CloudWatch logging unavailable: {e}")

    return root
