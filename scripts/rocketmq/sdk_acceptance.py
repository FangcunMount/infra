"""Required public Go SDK cases, inside ci-transactions' owned fixture only."""
import time


def run_go_sdk(start, absent, passed, sql, mongo_command):
    for storage in ("mysql", "mongo"):
        init = start("sdk-go", "init", storage=storage)
        init.wait("installed")
        init.finish()
        consumer = start("sdk-go", "consume", storage=storage)
        consumer.wait("ready")
        received = set()
        for action in ("commit", "rollback"):
            identity = "sdk-" + storage + "-" + action
            sender = start("sdk-go", "send", identity, storage=storage)
            sender.wait("half")
            absent(consumer, identity, 2)
            sender.send(action)
            sender.wait("finalized", identity,
                        "committed" if action == "commit" else "aborted")
            sender.wait("closed")
            sender.finish()
            if action == "commit":
                consumer.wait("received", identity)
                received.add(identity)
            else:
                absent(consumer, identity, 3)
            passed("public_go_" + storage + "_half_then_" + action)

        for mode, exit_code, decision in (("crash-committed", 23, "commit"),
                                           ("crash-prepared", 22, "rollback")):
            identity = "sdk-" + storage + "-" + mode
            sender = start("sdk-go", mode, identity, storage=storage)
            sender.wait("half")
            absent(consumer, identity, 1)
            sender.send("commit")
            sender.finish(expected=exit_code)  # real OS exit; no final RPC/Close
            recovery = start("sdk-go", "recover", storage=storage)
            recovery.wait("ready")  # idle instance, no Reserve or Execute
            recovery.wait("checked", decision=decision, timeout=100)
            if decision == "commit":
                consumer.wait("received", identity)
                received.add(identity)
            else:
                absent(consumer, identity, 5)
            recovery.send("stop")
            recovery.wait("closed")
            recovery.finish()
            passed("public_go_" + storage + "_new_instance_" + mode)
        if storage == "mysql":
            rows = sql("SELECT id FROM sdk_business ORDER BY id;").splitlines()
        else:
            rows = mongo_command('db.getSiblingDB("sdkprobe").sdk_business.find({}, {_id:1}).sort({_id:1}).forEach(x=>print(x._id))').splitlines()
        if set(rows) != received or len(rows) != len(received):
            raise RuntimeError("public SDK business effects differ from exact committed identity set")
        consumer.drain()
        observed = {e["id"] for e in consumer.events if e.get("event") == "received"}
        if observed != received:
            raise RuntimeError("public SDK observer identity set mismatch")
        consumer.close()
        passed("public_go_" + storage + "_exact_business_and_wire_set")


def assert_absent(consumer, identity, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        consumer.drain()
        if any(e.get("event") in ("failed", "exited") for e in consumer.events):
            raise RuntimeError("public SDK observer failed")
        if any(e.get("event") == "received" and e.get("id") == identity for e in consumer.events):
            raise RuntimeError("uncommitted public SDK half became visible")
        time.sleep(.05)
