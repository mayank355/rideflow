import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging_config import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Wraps every incoming request. Generates a unique request_id (so if
    something goes wrong, every log line related to THIS specific
    request — even across multiple internal function calls — can be
    found by filtering on one id, instead of guessing which log lines
    belong together from timestamps alone).

    Attaches request_id to request.state so route handlers COULD also
    use it in their own logging if needed (not required for this to
    work, but available).
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.monotonic()

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        response.headers["X-Request-ID"] = request_id
        return response
