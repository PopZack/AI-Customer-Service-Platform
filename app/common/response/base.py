"""统一响应格式:所有 API 返回 {code, message, data} 结构。"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseBase(BaseModel, Generic[T]):
    """统一 API 响应体。

    - code: 0 表示成功,非 0 表示业务/系统错误
    - message: 人类可读的提示
    - data: 业务数据,可选
    """

    code: int = 0
    message: str = "success"
    data: T | None = None


def success(data: Any = None, message: str = "success") -> ResponseBase:
    """构造成功响应。"""
    return ResponseBase(code=0, message=message, data=data)


def error(code: int = -1, message: str = "error", data: Any = None) -> ResponseBase:
    """构造错误响应。"""
    return ResponseBase(code=code, message=message, data=data)
