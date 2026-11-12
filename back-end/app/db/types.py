from datetime import datetime, timezone

from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """MySQL lưu DATETIME theo UTC; Python nhận datetime có múi giờ."""

    impl = DATETIME(fsp=6)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
