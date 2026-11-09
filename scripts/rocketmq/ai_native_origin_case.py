"""Owned integration case, loaded by the exact AI checkout's locked pytest."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys

import pytest
from reliable_messaging.transaction import Decision, FinalOutcome, LocalOutcome, StoreChecker, execution_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from qs_ai.infrastructure.persistence.mysql.native_limit import MySQLNativeLimits
from qs_ai.infrastructure.persistence.mysql.transaction_schema import witness
from qs_ai.infrastructure.workflow_transport.native_limit import parse_native_limit_evidence
from tests.integration.rocketmq_state_host import (
    broker, host, keys, kit, original, requested, required_broker,
    required_disposable_primary, setup_run,
)

pytestmark = pytest.mark.integration


def emit(event, **facts):
    print("AI_NATIVE_ORIGIN " + json.dumps(dict(event=event, **facts)), flush=True)


async def receive(expected):
    command = await asyncio.wait_for(asyncio.to_thread(sys.stdin.readline), timeout=180)
    assert command.strip() == expected


async def read_witness(host, execution):
    key = execution_key(execution.plan.owner, execution.plan.operation_id,
                        execution.writer_epoch, execution.fence)
    async with host.tx.open() as db:
        return (await db.execute(select(witness).where(witness.c.execution_key == key))).mappings().one()


async def test_original_ai_root_reaches_native_limit(broker, required_broker):
    broker.runtime.pause = True
    task = asyncio.create_task(broker.worker.once())
    try:
        await asyncio.wait_for(broker.runtime.entered.wait(), timeout=30)
        reserved = await broker.host.store.lookup(broker.intent.request)
        execution = reserved.execution
        assert execution.plan.owner == "ai.mysql"
        branch, = execution.plan.branches
        reference, = execution.references
        before = await read_witness(broker.host, execution)
        assert before["state"] == before["half_outcome"] == b"prepared"
        assert before["broker_message_id"] and before["broker_transaction_id"]
        assert not broker.messages
        emit("half", key=branch.message.message_id)
        await receive("commit")
        broker.runtime.release.set()
        assert await asyncio.wait_for(task, timeout=40)
        result = broker.runtime.results[-1]
        assert result.local is LocalOutcome.COMMITTED
        branch_result, = result.branches
        assert branch_result.final is FinalOutcome.UNKNOWN
        await broker.runtime.close(grace_seconds=20)
        assert broker.runtime._sender.stats()["stopped"]
        assert broker.runtime.calls == 1
        broker.gateway.generate_messages.assert_not_called()
        broker.recorder.flush.assert_not_called()
        after = await read_witness(broker.host, execution)
        assert after["state"] == b"committed"
        assert all(after[key] == before[key] for key in (
            "reference", "broker_message_id", "broker_transaction_id", "half_recorded_at",
        ))
        assert await StoreChecker(broker.host.store).check(reference) is Decision.COMMIT
        stored = await broker.host.archives.read_committed(branch.message.message_id)
        assert stored is not None and stored.wire == branch.wire
        emit("closed", reference_sha256=hashlib.sha256(after["reference"]).hexdigest(),
             wire_sha256=branch.wire_hash.hex())
        await receive("record")
        path = Path(required_broker["native_origin_evidence"])
        assert path.is_absolute() and path.stat().st_mode & 0o777 == 0o600
        raw = path.read_bytes()
        evidence = parse_native_limit_evidence(raw, hashlib.sha256(raw).digest())
        assert len(evidence.indices) == 1
        sessions = async_sessionmaker(broker.host.tx.database.engine, expire_on_commit=False)
        native = MySQLNativeLimits(sessions, broker.host.store.binding, "m3-1")
        await native.record(evidence)
        await native.record(evidence)
        assert await native.read_native_limit()
        assert await read_witness(broker.host, execution) == after
        assert not broker.messages
        emit("blocked", evidence_sha256=evidence.digest.hex())
    finally:
        broker.runtime.release.set()
        await asyncio.gather(task, return_exceptions=True)
