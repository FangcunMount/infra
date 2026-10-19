"""Disposable driver proof. No SDK public API or production business logic."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

from rocketmq.grpc_protocol import TransactionResolution
from rocketmq.v5.client import ClientConfiguration, Credentials
from rocketmq.v5.model import Message
from rocketmq.v5.producer import Producer, TransactionChecker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def emit(event, identity="", decision=""):
    print("TXPROBE " + json.dumps({"event": event, "id": identity,
                                  "decision": decision}), flush=True)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("send", "recover"), required=True)
    parser.add_argument("--id", default="")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    loop = asyncio.get_running_loop()
    engine = create_async_engine(config["mysql_url"], pool_size=2, max_overflow=0,
                                 connect_args={"connect_timeout": 1}, pool_pre_ping=True)

    async def check(message):
        identity = message.properties.get("probe_id", "")
        props = message.properties
        if (props.get("owner") != config["owner"] or message.topic != config["topic"]
                or props.get("wire_hash") != hashlib.sha256(message.body).hexdigest()):
            emit("checked", identity, "unknown_identity")
            return TransactionResolution.TRANSACTION_RESOLUTION_UNSPECIFIED
        try:
            async with asyncio.timeout(1):
                async with engine.connect() as connection:
                    result = await connection.execute(text(
                        "SELECT state FROM witness WHERE id=:id AND owner=:owner "
                        "AND wire_hash=:wire_hash"),
                        {"id": identity, "owner": config["owner"],
                         "wire_hash": props["wire_hash"]})
                    state = result.scalar_one_or_none()
        except Exception:
            emit("checked", identity, "unknown_database")
            return TransactionResolution.TRANSACTION_RESOLUTION_UNSPECIFIED
        decision = {"COMMITTED": (TransactionResolution.COMMIT, "commit"),
                    "ABORTED": (TransactionResolution.ROLLBACK, "rollback")}.get(state)
        if decision:
            emit("checked", identity, decision[1])
            return decision[0]
        emit("checked", identity, "unknown_prepared" if state else "unknown_missing")
        return TransactionResolution.TRANSACTION_RESOLUTION_UNSPECIFIED

    class Checker(TransactionChecker):
        def check(self, message):
            # The driver callback is a worker thread; all AsyncSession/engine I/O
            # remains on the host loop. The upstream queue is NOT yet SDK-bounded.
            future = asyncio.run_coroutine_threadsafe(check(message), loop)
            try:
                return future.result(timeout=2)
            except Exception:
                future.cancel()
                emit("checked", message.properties.get("probe_id", ""), "unknown_timeout")
                return TransactionResolution.TRANSACTION_RESOLUTION_UNSPECIFIED

    producer = Producer(ClientConfiguration(config["endpoint"],
                        Credentials(config["accesskey"], config["secretkey"]),
                        request_timeout=5), topics={config["topic"]},
                        checker=Checker(), tls_enable=True)

    def start():
        producer.startup()
        producer._retrieve_topic_route_data(config["topic"])
        if not producer._init_settings_event.wait(timeout=5):
            raise TimeoutError("server settings missing")

    try:
        await asyncio.to_thread(start)
        emit("ready", decision="producer")
        if args.mode == "recover":
            await asyncio.to_thread(sys.stdin.readline)
            return
        body = ("tx:" + args.id).encode()
        values = {"id": args.id, "owner": config["owner"],
                  "wire_hash": hashlib.sha256(body).hexdigest()}
        async with engine.begin() as connection:
            await connection.execute(text(
                "INSERT INTO witness(id,owner,wire_hash,state) "
                "VALUES(:id,:owner,:wire_hash,'PREPARED')"), values)
        transaction = producer.begin_transaction()
        message = Message()
        message.topic, message.body = config["topic"], body
        message.keys = args.id
        for key, value in (("probe_id", args.id), ("owner", config["owner"]),
                           ("wire_hash", values["wire_hash"])):
            message.add_property(key, value)
        receipt = await asyncio.to_thread(producer.send, message, transaction)
        if not receipt or not receipt.message_id or not receipt.transaction_id:
            raise RuntimeError("half not confirmed")
        emit("half", args.id, "confirmed")
        action = (await asyncio.to_thread(sys.stdin.readline)).strip()
        if action == "crash-prepared":
            os._exit(23)
        if action not in ("commit", "rollback", "crash-committed", "lost-commit-response"):
            raise ValueError("missing/invalid decision")
        state = "ABORTED" if action == "rollback" else "COMMITTED"
        async with engine.begin() as connection:
            if state == "COMMITTED":
                await connection.execute(text("INSERT INTO effects(id) VALUES(:id)"), values)
            result = await connection.execute(text(
                "UPDATE witness SET state=:state WHERE id=:id AND owner=:owner "
                "AND wire_hash=:wire_hash AND state='PREPARED'"), dict(values, state=state))
            if result.rowcount != 1:
                raise RuntimeError("witness CAS failed")
        emit("local", args.id, state)
        if action == "crash-committed":
            os._exit(23)
        if action == "lost-commit-response":
            original = producer.end_transaction

            def discard(*values, **kwargs):
                original(*values, **kwargs)
                raise TimeoutError("test discarded real EndTransaction response")

            producer.end_transaction = discard
            try:
                await asyncio.to_thread(transaction.commit)
            except TimeoutError:
                emit("finalization_unknown", args.id, "response_discarded_after_real_rpc")
                os._exit(24)
            raise RuntimeError("response-loss fault did not fire")
        await asyncio.to_thread(transaction.rollback if action == "rollback" else transaction.commit)
        emit("finalized", args.id, state)
    finally:
        await asyncio.to_thread(producer.shutdown)
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        # Keep upstream exception messages/private DSNs out of shared CI output.
        emit("failed", decision="operation_failed")
        raise SystemExit(1)
