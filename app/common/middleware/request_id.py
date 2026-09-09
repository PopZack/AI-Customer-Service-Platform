"""请求 ID 中间件:为每个请求分配唯一 ID,贯穿日志与响应头。"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """生成或透传请求 ID。

    - 若客户端携带 X-Request-ID 则透传
    - 否则生成一个 uuid4 hex
    - 写入 request.state.request_id 供日志使用
    - 回写到响应头 X-Request-ID
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        response: Response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
