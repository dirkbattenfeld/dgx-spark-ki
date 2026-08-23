import traceback
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("libs.observability.system")

class ObservabilityExceptionMiddleware(BaseHTTPMiddleware):
    """Fängt Exceptions auf ASGI/Middleware-Ebene ab."""
    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as exc:
            tb_str = traceback.format_exc()
            logger.error(
                "💥 [ASGI-Exception] Unbehandelter Fehler bei %s %s:\n%s",
                request.method,
                request.url.path,
                tb_str
            )
            raise exc

async def global_exception_handler(request: Request, exc: Exception):
    """Fängt unbehandelte Exception innerhalb von FastAPI-Routen/Wrappern ab."""
    tb_str = traceback.format_exc()
    logger.error(
        "💥 [Endpoint-Exception] Unbehandelter Fehler bei %s %s:\n%s",
        request.method,
        request.url.path,
        tb_str
    )
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal Server Error",
            "details": str(exc),
            "path": request.url.path
        }
    )