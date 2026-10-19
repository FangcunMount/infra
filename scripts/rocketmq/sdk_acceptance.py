"""Required public Go SDK cases, inside ci-transactions' owned fixture only."""
import time


def run_go_sdk(start, absent, passed, sql, mongo_command, pause_mysql, wrong_ca):
    for storage in ("mysql", "mongo"):
        consumer = start("sdk-go", "consume", storage=storage)
        consumer.wait("ready")
        received, business = set(), set()
        for action in ("commit", "rollback"):
            identity = "sdk-" + storage + "-" + action
            sender = start("sdk-go", "send", identity, storage=storage, branches=3)
            sender.wait("half")
            for i in range(3):
                absent(consumer, identity + "-b" + str(i), 1)
            sender.send(action)
            sender.wait("finalized", identity,
                        "committed" if action == "commit" else "aborted")
            sender.wait("closed")
            sender.finish()
            if action == "commit":
                for i in range(3):
                    message_id = identity + "-b" + str(i)
                    consumer.wait("received", message_id)
                    received.add(message_id)
                business.add(identity)
            else:
                for i in range(3):
                    absent(consumer, identity + "-b" + str(i), 1)
            passed("public_go_" + storage + "_half_then_" + action)

        for mode, exit_code, decision in (("crash-committed", 23, "commit"),
                                           ("crash-prepared", 22, "rollback")):
            identity = "sdk-" + storage + "-" + mode
            sender = start("sdk-go", mode, identity, storage=storage, branches=3)
            sender.wait("half")
            for i in range(3):
                absent(consumer, identity + "-b" + str(i), .25)
            sender.send("commit")
            sender.finish(expected=exit_code)  # real OS exit; no final RPC/Close
            recovery = start("sdk-go", "recover", storage=storage)
            recovery.wait("ready")  # idle instance, no Reserve or Execute
            recovery.wait("checked", decision=decision, timeout=100)
            if decision == "commit":
                for i in range(3):
                    message_id = identity + "-b" + str(i)
                    consumer.wait("received", message_id)
                    received.add(message_id)
                business.add(identity)
            else:
                for i in range(3):
                    absent(consumer, identity + "-b" + str(i), 1)
            recovery.send("stop")
            recovery.wait("closed")
            recovery.finish()
            passed("public_go_" + storage + "_new_instance_" + mode)
        if storage == "mysql":
            failed_start = start("sdk-go", "recover", storage=storage, trust=wrong_ca)
            failed_start.wait("closed", decision="failed_start_drained")
            failed_start.finish(expected=1)
            passed("public_go_untrusted_ca_startup_really_drained")
            identity = "sdk-mysql-isolation"
            sender = start("sdk-go", "isolation", identity, branches=3)
            sender.wait("isolated")
            sender.wait("half")
            sender.send("commit")
            sender.wait("closed")
            sender.finish()
            for i in range(3):
                message_id = identity + "-b" + str(i)
                consumer.wait("received", message_id)
                received.add(message_id)
            business.add(identity)
            passed("public_go_same_process_client_isolation")
            identity = "sdk-mysql-database-outage"
            recovery = start("sdk-go", "recover")
            recovery.wait("ready")
            sender = start("sdk-go", "crash-committed", identity, branches=3)
            sender.wait("half")
            sender.send("commit")
            sender.finish(expected=23)
            pause_mysql(True)
            try:
                recovery.wait("checked", decision="unknown", timeout=35)
                for i in range(3):
                    absent(consumer, identity + "-b" + str(i), .25)
            finally:
                pause_mysql(False)
            recovery.wait("checked", decision="commit", timeout=60)
            for i in range(3):
                message_id = identity + "-b" + str(i)
                consumer.wait("received", message_id)
                received.add(message_id)
            business.add(identity)
            recovery.send("stop")
            recovery.wait("closed")
            recovery.finish()
            passed("public_go_real_database_outage_unknown_then_recovery")
        if storage == "mysql":
            rows = sql("SELECT id FROM sdk_business ORDER BY id;").splitlines()
        else:
            rows = mongo_command('db.getSiblingDB("sdkprobe").sdk_business.find({}, {_id:1}).sort({_id:1}).forEach(x=>print(x._id))').splitlines()
        if set(rows) != business or len(rows) != len(business):
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


def run_python_sdk(start, passed, sql, pause_mysql, wrong_ca):
    consumer = start("sdk-go", "consume", storage="mysql")
    consumer.wait("ready")
    received = set()
    for action in ("commit", "rollback"):
        identity = "py-sdk-" + action
        sender = start("sdk-python", "send", identity)
        sender.wait("half")
        assert_absent(consumer, identity, 2)
        sender.send(action)
        sender.wait("finalized", identity, "committed" if action == "commit" else "aborted")
        sender.wait("closed")
        sender.finish()
        if action == "commit":
            consumer.wait("received", identity)
            received.add(identity)
        else:
            assert_absent(consumer, identity, 3)
        passed("public_python_half_then_" + action)

    for language, recovery_language, mode, status, decision in (
        ("sdk-python", "sdk-python", "crash-committed", 23, "commit"),
        ("sdk-python", "sdk-python", "crash-prepared", 22, "rollback"),
        ("sdk-go", "sdk-python", "crash-committed", 23, "commit"),
        ("sdk-python", "sdk-go", "crash-committed", 23, "commit"),
    ):
        identity = "py-sdk-" + language + "-to-" + recovery_language + "-" + mode
        sender = start(language, mode, identity)
        sender.wait("half")
        assert_absent(consumer, identity, 1)
        sender.send("commit")
        sender.finish(expected=status)
        recovery = start(recovery_language, "recover")
        recovery.wait("ready")
        recovery.wait("checked", decision=decision, timeout=100)
        if decision == "commit":
            consumer.wait("received", identity)
            received.add(identity)
        else:
            assert_absent(consumer, identity, 5)
        recovery.send("stop")
        recovery.wait("closed")
        recovery.finish()
        passed("public_" + language + "_to_" + recovery_language + "_" + mode)

    identity = "py-sdk-database-outage"
    recovery = start("sdk-python", "recover")
    recovery.wait("ready")
    sender = start("sdk-go", "crash-committed", identity)
    sender.wait("half")
    sender.send("commit")
    sender.finish(expected=23)
    pause_mysql(True)
    try:
        recovery.wait("checked", decision="unknown", timeout=35)
        assert_absent(consumer, identity, 2)
    finally:
        pause_mysql(False)
    recovery.wait("checked", decision="commit", timeout=60)
    consumer.wait("received", identity)
    received.add(identity)
    recovery.send("stop")
    recovery.wait("closed")
    recovery.finish()
    passed("public_python_real_database_outage_unknown_then_recovery")
    failed_start = start("sdk-python", "recover", trust=wrong_ca)
    failed_start.wait("closed", decision="failed_start_drained")
    failed_start.finish(expected=1)
    passed("public_python_untrusted_ca_startup_really_drained")
    identity = "py-sdk-isolation"
    sender = start("sdk-python", "isolation", identity)
    sender.wait("isolated")
    sender.wait("half")
    sender.send("commit")
    sender.wait("closed")
    sender.finish()
    consumer.wait("received", identity)
    received.add(identity)
    passed("public_python_same_process_client_isolation")
    rows = sql("SELECT id FROM sdk_business WHERE id LIKE 'py-sdk-%' ORDER BY id;").splitlines()
    if set(rows) != received or len(rows) != len(received):
        raise RuntimeError("Python/cross-language SDK business effect set mismatch")
    consumer.drain()
    observed = {e["id"] for e in consumer.events if e.get("event") == "received"
                and e["id"].startswith("py-sdk-")}
    if observed != received:
        raise RuntimeError("Python/cross-language SDK original wire set mismatch")
    consumer.close()
    passed("public_python_cross_language_exact_business_and_wire_set")
