"""Repeated cancellation cannot release admission before a worker finishes."""

import asyncio
import threading

import pytest

from app.repositories.ai_quota_repository import SqlAlchemyAiQuotaRepository
from app.services.chat_service import _commit_message
from app.utils.errors import AppError
from test_ai_quiz_api import quiz_app

pytestmark = pytest.mark.anyio


async def cancel_again(task):
    for _ in range(3):
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done(), "The worker still owns its write/admission lease"


async def test_repeated_cancellation_drains_chat_commit():
    entered, finish = threading.Event(), threading.Event()
    committed = []
    def worker():
        entered.set()
        assert finish.wait(5)
        committed.append(True)
        return None
    task = asyncio.create_task(_commit_message(asyncio.to_thread(worker)))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await cancel_again(task)
        assert committed == []
    finally:
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert committed == [True]


async def test_repeated_cancellation_keeps_quiz_admission_until_worker_commit():
    async with quiz_app() as state:
        quota, service = state.app.state.ai_quota_service, state.app.state.quiz_service
        service._quota = quota
        entered, finish = threading.Event(), threading.Event()
        original = state.repository.create_quiz
        def worker(*args, **kwargs):
            entered.set()
            assert finish.wait(5)
            return asyncio.run(original(*args, **kwargs))
        async def delayed_save(*args, **kwargs):
            return await asyncio.to_thread(worker, *args, **kwargs)
        state.repository.create_quiz = delayed_save
        task = asyncio.create_task(service.generate_quiz(state.owner, state.topic_id, "easy"))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            await cancel_again(task)
            with pytest.raises(AppError) as caught:
                async with quota.generation(state.owner.id):
                    pytest.fail("The original save still owns this account's admission")
            assert caught.value.code == "AI_REQUEST_BUSY"
        finally:
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert len(state.repository._quizzes) == 1
        assert (await quota.get_quota(state.owner.id)).used == 1
        async with quota.generation(state.owner.id):
            pass


async def test_repeated_cancellation_drains_late_advisory_acquisition(monkeypatch):
    repository = SqlAlchemyAiQuotaRepository(None)
    entered, finish = threading.Event(), threading.Event()
    lease, released = object(), []
    def acquire(_):
        entered.set()
        assert finish.wait(5)
        return lease
    monkeypatch.setattr(repository, "_acquire", acquire)
    monkeypatch.setattr(SqlAlchemyAiQuotaRepository, "_release", staticmethod(released.append))
    async def run():
        async with repository.request_guard(1):
            pytest.fail("Cancelled admission must never start a provider request")
    task = asyncio.create_task(run())
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await cancel_again(task)
        assert released == []
    finally:
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert released == [lease]


async def test_repeated_cancellation_finishes_advisory_release(monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    lease, released = object(), []
    def release(value):
        entered.set()
        assert finish.wait(5)
        released.append(value)
    monkeypatch.setattr(SqlAlchemyAiQuotaRepository, "_release", staticmethod(release))
    task = asyncio.create_task(SqlAlchemyAiQuotaRepository._finish_release(lease))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await cancel_again(task)
        assert released == []
    finally:
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert released == [lease]
