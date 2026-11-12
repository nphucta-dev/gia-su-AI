from pydantic import BaseModel, Field

from app.schemas.auth import PublicUser


class ProfileUser(PublicUser):
    birth_year: int | None = Field(serialization_alias="birthYear")


class ProfileResponse(BaseModel):
    user: ProfileUser


class ProfileUpdateResponse(ProfileResponse):
    message: str
