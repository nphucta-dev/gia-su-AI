"""Schema cho các API cần đăng nhập."""

from pydantic import BaseModel

from app.schemas.auth import PublicUser


class MeResponse(BaseModel):
    user: PublicUser
