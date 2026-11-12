from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import mysql

from app.db.types import UTCDateTime


def test_local_time_saved_as_utc_and_loaded_with_timezone():
    dialect = mysql.dialect()
    date_type = UTCDateTime()
    local_time = datetime(2026, 11, 10, 15, 30, 12, 123456, tzinfo=timezone(timedelta(hours=7)))
    stored = date_type.bind_processor(dialect)(local_time)
    assert stored == datetime(2026, 11, 10, 8, 30, 12, 123456)
    assert stored.tzinfo is None

    loaded = date_type.result_processor(dialect, None)(stored)
    assert loaded == local_time
    assert loaded.tzinfo is timezone.utc


def test_nullable_and_naive_utc_datetimes():
    dialect = mysql.dialect()
    date_type = UTCDateTime()
    assert date_type.bind_processor(dialect)(None) is None
    assert date_type.result_processor(dialect, None)(None) is None
    naive_utc = datetime(2026, 11, 10, 8, 30)
    assert date_type.bind_processor(dialect)(naive_utc) == naive_utc
    assert date_type.result_processor(dialect, None)(naive_utc).tzinfo is timezone.utc
