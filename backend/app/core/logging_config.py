import json
import logging
from datetime import datetime, timezone

# Fields already present on every stdlib LogRecord — used to detect the "extra"
# fields a caller attached via logger.info(..., extra={...}), so those get
# surfaced as real JSON keys instead of getting silently dropped.
_STANDARD_RECORD_KEYS = set(vars(logging.makeLogRecord({})).keys())


class JSONFormatter(logging.Formatter):
    """One JSON object per line — parseable by any log aggregator (CloudWatch,
    Datadog, ELK) without a custom parsing rule, unlike a flat
    "%(asctime)s | %(levelname)s | ..." text line where level/logger/trace
    fields aren't queryable without regex."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_KEYS and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(*, debug: bool, log_format: str) -> None:
    """log_format="json" for production (log aggregator-friendly); anything
    else falls back to the original human-readable text format, which is
    what you actually want staring at a local terminal."""
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)
