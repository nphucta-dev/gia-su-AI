"""Dependency xác thực cho các API cần đăng nhập.

Dùng trong route::

    @router.get("/viec-can-dang-nhap")
    async def handler(user: Annotated[User, Depends(get_current_user)]): ...

    @router.get("/chi-admin", dependencies=[Depends(require_roles("ADMIN"))])
    async def admin_only(): ...

Máy chủ luôn tự kiểm tra quyền; việc ẩn/hiện trang ở front-end (router hash) không phải
hàng rào bảo mật.
"""

from __future__ import annotations

from typing import Annotated, Awaitable, Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.repositories.user_repository import User
from app.services.token_service import TokenService, invalid_token_error, not_authenticated_error
from app.utils.errors import AppError

# auto_error=False để tự trả lỗi theo định dạng thống nhất của API (NOT_AUTHENTICATED).
# Khai báo scheme này cũng làm /docs hiện nút "Authorize" để dán token thử gọi API.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token JWT: Authorization: Bearer <token>")


def get_token_service(request: Request) -> TokenService:
    return request.app.state.token_service


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    token_service: Annotated[TokenService, Depends(get_token_service)],
) -> User:
    """Xác thực token ở header Authorization và trả về người dùng hiện tại.

    Raises:
        AppError: 401 ``NOT_AUTHENTICATED`` (không có token), ``TOKEN_EXPIRED`` (hết hạn),
            ``INVALID_TOKEN`` (token sai, hoặc tài khoản của token không còn tồn tại);
            403 ``FORBIDDEN`` khi tài khoản đã bị vô hiệu hóa.
    """
    if credentials is None or not credentials.credentials:
        raise not_authenticated_error()

    payload = token_service.verify_access_token(credentials.credentials)

    user = await request.app.state.user_repository.find_by_id(payload.user_id)
    if user is None:
        # Token hợp lệ nhưng tài khoản đã bị xoá: coi như token không còn dùng được.
        raise invalid_token_error()
    if not user.is_active:
        raise AppError(403, "FORBIDDEN", "Tài khoản đã bị vô hiệu hóa.")
    return user


def require_roles(*roles: str) -> Callable[..., Awaitable[User]]:
    """Tạo dependency chỉ cho phép người dùng có một trong các vai trò đã nêu (403 nếu không)."""
    allowed = frozenset(roles)

    async def check_role(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed:
            raise AppError(403, "FORBIDDEN", "Bạn không có quyền thực hiện thao tác này.")
        return user

    return check_role
