"""Owned integration case, loaded by the exact AI checkout's locked pytest."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys

import pytest
from reliable_messaging.rocketmq import RocketMQSubscriber
from reliable_messaging.transaction import Decision, FinalOutcome, LocalOutcome, StoreChecker, execution_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from qs_ai.bootstrap.transaction_messaging import TransactionAdmissionClosed, make_transaction_sender
from qs_ai.bootstrap.transaction_protection import ProtocolProtectionError
from qs_ai.config import MessagingOptions
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


async def receive(expected, timeout=180):
    command = await asyncio.wait_for(asyncio.to_thread(sys.stdin.readline), timeout=timeout)
    assert command.strip() == expected


async def read_witness(host, execution):
    key = execution_key(execution.plan.owner, execution.plan.operation_id,
                        execution.writer_epoch, execution.fence)
    async with host.tx.open() as db:
        return (await db.execute(select(witness).where(witness.c.execution_key == key))).mappings().one()


async def start_recovery_observer(broker, branch):
    # A receive RPC interrupted by the owned Broker disconnection ends its
    # poller. Reuse the same authenticated handler, binding and group after
    # reconnect with a fresh subscriber, before the Go Checker can confirm.
    previous = broker.observer
    observer = RocketMQSubscriber(
        previous.config, previous.route.topic, previous.route.subscription,
        handler=previous.handler, failed_handler=previous.failed_handler,
        invalid_handler=previous.invalid_handler, retry_cap=1,
    )
    broker.resources.push_async_callback(observer.stop, grace_seconds=20)
    await observer.start()
    loop = asyncio.get_running_loop()
    acknowledged = asyncio.Event()
    actual_ack = observer._driver.client.ack

    def ack(raw, *args, **kwargs):
        result = actual_ack(raw, *args, **kwargs)
        if bytes(raw.body) == branch.wire:
            loop.call_soon_threadsafe(acknowledged.set)
        return result

    observer._driver.client.ack = ack
    emit("recovery_observer_started")
    return acknowledged


async def verify_reopen(broker, config, sessions, native, execution, after, branch, acknowledged, tmp_path):
    # The stable Go checker has already drained; now start a fresh, paused AI owner.
    credentials, routes = tmp_path / "credentials.json", tmp_path / "routes.json"
    credentials.write_text(json.dumps(config["ai"]))
    routes.write_text(json.dumps({"version": 2, "routes": config["routes"]}))
    for path in (credentials, routes):
        path.chmod(0o600)
    binding = broker.host.store.binding
    options = MessagingOptions(
        provider="rocketmq", publish_enabled=False,
        rocketmq=dict(endpoint=config["endpoint"], credentials_file=str(credentials),
                      routes_file=str(routes), ca_file=config["ca_file"]),
        transactions={"ai.mysql": dict(store_id=binding.store_id, writer_epoch=binding.writer_epoch,
                                       route_revision="m3-1")},
    )
    replacement = make_transaction_sender(options, sessions)
    try:
        await receive("observe", timeout=350)
        await replacement.start()
        emit("replacement_started")
        blocked = replacement.protection_stats()
        assert blocked["fresh"] and blocked["native_limit_active"]
        assert replacement._sender.stats()["ready"]
        with pytest.raises(TransactionAdmissionClosed):
            replacement.set_admission(True)
        with pytest.raises(ProtocolProtectionError):
            replacement.review_protection(blocked["generation"], "fixture-before-resolution")
        emit("replacement_blocked")
        await broker.complete()
        emit("first_wire_seen")
        assert broker.messages == {branch.message.message_id: branch.wire_hash.hex()}
        await asyncio.wait_for(acknowledged.wait(), timeout=20)
        emit("observed", wire_sha256=branch.wire_hash.hex(), broker_ack=True)
        await receive("verify", timeout=350)
        assert not await native.read_native_limit()
        async with asyncio.timeout(25):
            while True:
                status = replacement.protection_stats()
                if status["fresh"] and not status["native_limit_active"]:
                    break
                await asyncio.sleep(0.05)
        assert status["protected"]
        with pytest.raises(TransactionAdmissionClosed):
            replacement.set_admission(True)
        replacement.review_protection(status["generation"], "fixture-named-ai-reopen")
        assert not replacement.stats()["ready"]
        replacement.set_admission(True)
        assert replacement.stats()["ready"]
        saved = await replacement.reserve(broker.intent.request, execution.plan)
        assert not saved.acquired and saved.execution.references == execution.references
        assert replacement._sender.stats()["half_prepared_results"] == 0
        final = await read_witness(broker.host, execution)
        assert final["final_outcome"] == b"commit_confirmed"
        assert all(final[key] == after[key] for key in (
            "reference", "broker_message_id", "broker_transaction_id", "half_recorded_at",
        ))
        archived = await broker.host.archives.read_committed(branch.message.message_id)
        assert archived is not None and archived.wire == branch.wire
    finally:
        await replacement.close(grace_seconds=20)
    assert replacement.stats()["stopped"]
    emit("reopened", original_wire_preserved=True, no_new_half=True)


async def test_original_ai_root_reaches_native_limit(broker, required_broker, tmp_path):
    managed = required_broker.get("native_origin_managed") is True
    if managed:
        await broker.observer.stop(grace_seconds=20)
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
        metadata = {}
        if managed:
            metadata = dict(
                operation_id=execution.plan.operation_id, branch_id=branch.branch_id,
                fence=execution.fence, store_id=broker.host.store.binding.store_id,
                run_id=str(broker.scope.run_id),
            )
        emit("half", key=branch.message.message_id, **metadata)
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
        await receive("record", timeout=required_broker.get("native_origin_record_timeout", 180))
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
        if managed:
            acknowledged = await start_recovery_observer(broker, branch)
        emit("blocked", evidence_sha256=evidence.digest.hex())
        if managed:
            await verify_reopen(broker, required_broker, sessions, native, execution, after, branch, acknowledged, tmp_path)
    finally:
        broker.runtime.release.set()
        await asyncio.gather(task, return_exceptions=True)
