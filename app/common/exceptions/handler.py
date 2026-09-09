"""全局异常处理:把各类异常统一转换为 ResponseBase 格式。"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.response.base import error

logger = logging.getLogger("app.exceptions")


class AppException(Exception):
    """业务异常基类:业务逻辑中主动抛出,携带 code + message。"""

    def __init__(self, code: int = -1, message: str = "业务异常"):
        self.code = code
        self.message = message
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(AppException)
    async def _app_exception_handler(request: Request, exc: AppException):
        logger.warning(
            "业务异常 %s %s -> code=%s msg=%s",
            request.method,
            request.url.path,
            exc.code,
            exc.message,
        )
        return JSONResponse(
            status_code=400,
            content=error(exc.code, exc.message).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError):
        logger.warning("参数校验失败 %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=422,
            content=error(422, "参数校验失败", data=exc.errors()).model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        # 统一 404/405 等为 {code, message, data}
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=error(exc.status_code, message).model_dump(),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        logger.exception(
            "未处理异常 %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content=error(500, "服务器内部错误").model_dump(),
        )
