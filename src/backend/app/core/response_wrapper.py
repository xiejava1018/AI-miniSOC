"""
响应包装器 - 统一API响应格式

将后端响应统一包装为前端期望的格式:
{
    "code": 0,          // 0 = 成功, 非0 = 错误
    "msg": "success",   // 消息
    "data": { ... }     // 实际数据
}
"""

import json
from typing import Any
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ResponseWrapperMiddleware(BaseHTTPMiddleware):
    """统一响应格式中间件"""

    async def dispatch(self, request: Request, call_next):
        # 跳过文档和静态资源
        if request.url.path in ("/docs", "/redoc", "/openapi.json"):
            return await call_next(request)
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        response = await call_next(request)

        # 只处理 JSON 响应
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # 读取响应体
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # 复制响应头, 排除 content-length(新响应体长度不同)
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}

        # 如果是错误响应(4xx, 5xx), 包装为统一错误格式
        if response.status_code >= 400:
            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                data = {"detail": body.decode("utf-8", errors="replace")}

            error_msg = data.get("detail", data.get("message", "请求失败"))
            wrapped = {
                "code": response.status_code,
                "msg": error_msg,
                "data": None
            }
            return JSONResponse(
                content=wrapped,
                status_code=200,  # 统一返回200, 通过code区分错误
                headers=headers
            )

        # 成功响应包装
        try:
            data = json.loads(body) if body else None
        except json.JSONDecodeError:
            data = body.decode("utf-8", errors="replace")

        # 如果已经是包装格式, 不再重复包装
        if isinstance(data, dict) and "code" in data and "msg" in data and "data" in data:
            return JSONResponse(
                content=data,
                status_code=200,
                headers=headers
            )

        wrapped = {
            "code": 200,
            "msg": "success",
            "data": data
        }

        return JSONResponse(
            content=wrapped,
            status_code=200,
            headers=headers
        )
