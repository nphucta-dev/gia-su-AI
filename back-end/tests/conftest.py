import pytest


@pytest.fixture
def anyio_backend():
    # Các test async chỉ chạy với asyncio (plugin anyio đi kèm Starlette).
    return "asyncio"
