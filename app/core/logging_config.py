import logging
import json
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """
    Renders every log record as a single line of JSON instead of plain
    text -- machine-parseable by tools like Datadog/ELK/CloudWatch
    Insights, so you can query "every log where request_id = X" instead
    of grepping text.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        for field in ("request_id", "user_id", "user_role", "path", "method", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging():
    """
    Call once at app startup.

    THE BUG, and the actual fix: logging has a PARENT/CHILD hierarchy.
    "uvicorn.error" is a CHILD of "uvicorn", which is a child of the
    ROOT logger. By default, a log record propagates UP through every
    ancestor logger that also has a handler attached -- so if you attach
    a handler to "uvicorn.error" AND to "uvicorn" AND to root, the SAME
    log line gets printed three times, once per handler it passes
    through on its way up.

    The correct fix is the opposite of what you might first guess: don't
    attach the handler to multiple loggers in the hierarchy. Attach it
    ONCE, to the root logger. Every other logger (uvicorn, uvicorn.error,
    our own "rideflow" logger) has no handler of its own and simply lets
    its records propagate up to root, where they're formatted and
    printed exactly once.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    # Uvicorn's per-request access log ("GET /health 200 OK") is fully
    # redundant with our own RequestLoggingMiddleware, which logs the
    # same event with MORE structure (request_id, duration_ms). Disable
    # it entirely rather than reformat it.
    logging.getLogger("uvicorn.access").disabled = True

    # CRITICAL: do NOT set .handlers on "uvicorn" or "uvicorn.error" here.
    # Leave them with zero handlers of their own -- they will propagate
    # to root automatically (propagate=True is the default), and root's
    # single handler is the only one that ever actually prints anything.
    # This is what actually eliminates the duplication.


logger = logging.getLogger("rideflow")
