"""Explicit v2 resource provisioning with a complete read-before-write preflight.

Uses pinned 5.5.1 exportMetadata/listUser/getAcl formats. Existing resource or
principal conflicts are refused; no implicit type conversion/credential rotation.
"""
import json
import hashlib
import re
import secrets
import subprocess
import time

from routes import permissions_v2, validate


class ProvisionReadbackError(RuntimeError):
    """Bounded, nonsecret evidence; never carries raw metadata or credentials."""
    def __init__(self, missing, observations=None):
        super().__init__('provision_readback_incomplete')
        topics, groups, users, grants = missing
        names = dict(topics=[row[0] for row in topics], groups=groups, principals=users,
                     grants=[role + ':' + resource for role, resource, _ in grants])
        self.audit_diagnostic = {
            'code': 'provision_readback_incomplete',
            'missing_counts': {key: len(rows) for key, rows in names.items()},
            'missing_identity_sha256': {
                key: [hashlib.sha256(name.encode()).hexdigest() for name in sorted(rows)[:256]]
                for key, rows in names.items()},
            'identity_hashes_truncated': any(len(rows) > 256 for rows in names.values()),
            'mutation_retry_attempted': False,
        }
        if observations is not None:
            self.audit_diagnostic['observations'] = observations


def verify_readback(admin, directory, manifest, accounts, *, previous=None):
    """At most three authoritative read rounds; never retry a mutation or conflict."""
    observations = []
    for attempt in range(1, 4):
        after, users = admin.metadata(directory), admin.users()
        acls = {accounts[role]['username']: admin.acl(accounts[role]['username'])
                for role in manifest.get('accounts', {})}
        # Conflicts, missing original responsibilities and credential drift raise
        # immediately. Only incomplete new-resource visibility can be reread.
        missing = preflight(manifest, accounts, after, users, acls, previous=previous)
        observations.append(dict(attempt=attempt, missing_counts={
            key: len(rows) for key, rows in zip(('topics', 'groups', 'principals', 'grants'), missing)}))
        if not any(missing):
            return dict(attempts=attempt, observations=observations, mutation_retry_attempted=False)
        if attempt < 3:
            time.sleep(1)
    raise ProvisionReadbackError(missing, observations)


class Admin:
    def __init__(self, container):
        self.container = container
        self.operations = 0

    def docker(self, *arguments, required=True):
        try:
            result = subprocess.run(["docker", "exec", self.container, *arguments],
                                    capture_output=True, text=True, timeout=45)
        except (subprocess.TimeoutExpired, OSError):
            raise RuntimeError("private Broker operation timed out or unavailable") from None
        if required and result.returncode:
            raise RuntimeError("private Broker operation failed")
        return result

    def __call__(self, operation, *params, mutation=False):
        result = self.docker("java", "-Xms32m", "-Xmx128m", "-XX:MaxDirectMemorySize=32m", "-cp",
            "/opt/rocketmq/conf:/opt/rocketmq/lib/*", "org.apache.rocketmq.tools.command.MQAdminStartup",
            operation, "-b", "127.0.0.1:10911", *params)
        if "Exception" in result.stdout + result.stderr or "command failed" in result.stdout + result.stderr:
            raise RuntimeError("Broker administrative operation did not complete")
        if mutation:
            if " success." not in result.stdout:
                raise RuntimeError("Broker mutation missing positive completion")
            self.operations += 1
        return result.stdout

    def metadata(self, directory):
        tables = {}
        for flag, filename, table in (("-t", "topic.json", "topicConfigTable"),
                                      ("-g", "subscriptionGroup.json", "subscriptionGroupTable")):
            output = self("exportMetadata", flag, "-f", directory)
            if f"export {directory}/{filename} success" not in output:
                raise RuntimeError("metadata snapshot missing positive completion")
            path = directory + "/" + filename
            self.docker("chmod", "600", path)
            document = json.loads(self.docker("cat", path).stdout)
            if not isinstance(document.get(table), dict):
                raise RuntimeError("unrecognized pinned Broker metadata schema")
            tables[table] = document[table]
        return tables

    def users(self):
        output = self("listUser")
        rows, header = {}, False
        for line in output.splitlines():
            parts = line.split()
            if parts and parts[0] == "#UserName":
                header = True
                continue
            if not header or not parts:
                continue
            if len(parts) != 4:
                raise RuntimeError("unrecognized private principal snapshot")
            if parts[0] in rows:
                raise RuntimeError("duplicate principal snapshot")
            rows[parts[0]] = tuple(parts[1:])
        if not header or not any(row[1].lower() == "super" for row in rows.values()):
            raise RuntimeError("authoritative principal snapshot missing")
        return rows

    def acl(self, username):
        output = self("getAcl", "-s", "User:" + username)
        return parse_acl(output, "User:" + username)


def parse_acl(output, subject):
    permissions, header = {}, False
    pattern = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\[[^]]*\])\s+(\[[^]]*\]|null)\s+(\S+)\s*$")
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("#Subject"):
            header = True
            continue
        if not header:
            continue
        if not line or line == subject:
            continue
        match = pattern.fullmatch(line)
        if not match:
            raise RuntimeError("unrecognized private ACL snapshot")
        actual, policy, resource, actions, sources, decision = match.groups()
        if actual != subject or policy.lower() != "custom" or decision.lower() != "allow" or sources not in ("[]", "null", "[*]") or resource in permissions:
            raise RuntimeError("existing ACL contains conflicting policy or restriction")
        permissions[resource] = {{"pub":"Pub","get":"Get","sub":"Sub"}.get(action.strip().lower(), action.strip()) for action in actions[1:-1].split(",") if action.strip()}
    if not header and output.strip():
        raise RuntimeError("unrecognized empty ACL snapshot")
    return permissions


def desired_topics(manifest):
    options = manifest["topic_options"]
    return {r["physical_topic"]: {"readQueueNums": options["read_queue_nums"],
            "writeQueueNums": options["write_queue_nums"], "perm": options["perm"],
            "message_type": r["message_type"]} for r in manifest["routes"]}


def preflight(manifest, accounts, metadata, users, acls, *, previous=None):
    """Returns only missing resources. All conflicts abort before any mutation."""
    old_permissions = None
    if previous is not None:
        from readable_transition import validate_transition
        old_permissions = validate_transition(previous, manifest)
        if set(accounts) != set(manifest['accounts']):
            raise ValueError('exact reviewed existing application accounts required')
        # Existing old resources are a required baseline, never repaired or
        # recreated silently by preparation of their replacements.
        for topic, expected in desired_topics(previous).items():
            actual = metadata['topicConfigTable'].get(topic)
            if (actual is None or any(actual.get(key) != expected[key]
                    for key in ('readQueueNums', 'writeQueueNums', 'perm'))
                    or actual.get('attributes', {}).get('message.type') != expected['message_type']):
                raise RuntimeError('prior topic baseline missing or changed')
        for group in {r['consumer_group'] for r in previous['routes'] if r.get('consumer_group')}:
            actual = metadata['subscriptionGroupTable'].get(group)
            if (actual is None or actual.get('retryQueueNums') != previous['group_options']['retry_queue_nums']
                    or actual.get('consumeEnable') is not True):
                raise RuntimeError('prior group baseline missing or changed')
    missing_topics, missing_groups, missing_users, missing_acls = [], [], [], []
    for topic, expected in desired_topics(manifest).items():
        actual = metadata["topicConfigTable"].get(topic)
        if actual is None:
            missing_topics.append((topic, expected))
        elif (any(actual.get(k) != expected[k] for k in ("readQueueNums", "writeQueueNums", "perm"))
              or actual.get("attributes", {}).get("message.type") != expected["message_type"]):
            raise RuntimeError("existing topic type or configuration conflicts")
    retry = manifest["group_options"]["retry_queue_nums"]
    for group in sorted({r["consumer_group"] for r in manifest["routes"] if r.get("consumer_group")}):
        actual = metadata["subscriptionGroupTable"].get(group)
        if actual is None:
            missing_groups.append(group)
        elif actual.get("retryQueueNums") != retry or actual.get("consumeEnable") is not True:
            raise RuntimeError("existing subscription group configuration conflicts")
    usernames, passwords = set(), set()
    for role, grants in manifest.get("accounts", {}).items():
        account = accounts[role]
        username, password = account["username"], account["password"]
        if (not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", username) or len(password) < 32
            or any(c.isspace() for c in password) or username in usernames or password in passwords):
            raise ValueError("distinct application principals with private credentials required")
        usernames.add(username); passwords.add(password)
        existing = users.get(username)
        if existing is None:
            if previous is not None:
                raise RuntimeError('prior application principal missing; creation refused')
            missing_users.append(role)
        elif existing[0] != password or existing[1].lower() != "normal" or existing[2].lower() != "enable":
            raise RuntimeError("existing principal differs; credential rotation refused")
        desired = permissions_v2(manifest, grants)
        current = acls.get(username, {})
        if old_permissions is not None:
            from readable_transition import merged_permissions
            desired = merged_permissions(manifest, role, old_permissions)
            if any(current.get(resource) != actions for resource, actions in old_permissions[role].items()):
                raise RuntimeError('prior application ACL missing or changed')
        if any(resource not in desired or actions != desired[resource] for resource, actions in current.items()):
            raise RuntimeError("existing principal ACL exceeds or conflicts with reviewed grants")
        for resource, actions in desired.items():
            if resource not in current:
                missing_acls.append((role, resource, actions))
    return missing_topics, missing_groups, missing_users, missing_acls


def provision(container, manifest, accounts, *, previous=None):
    if manifest.get('version') not in (2, 3):
        raise ValueError('typed manifest version2 or version3 required')
    validate(manifest)
    if previous is not None:
        from readable_transition import validate_transition
        validate_transition(previous, manifest)
    admin = Admin(container)
    # Shared by cooperating infra invocations, including different host clients.
    # A stale lock is refused; this tool never steals/deletes another invocation's lock.
    lock = "/tmp/reliable-messaging-provision-v2.lock"
    if admin.docker("mkdir", "-m", "700", lock, required=False).returncode:
        raise RuntimeError("Broker v2 provision lock busy; metadata changes must be serialized")
    directory = lock + "/snapshot-" + secrets.token_hex(8)
    try:
        admin.docker("mkdir", "-m", "700", directory)
        metadata, users = admin.metadata(directory), admin.users()
        acls = {a["username"]: admin.acl(a["username"]) for role, a in accounts.items()
                if role in manifest.get("accounts", {}) and a["username"] in users}
        topics, groups, principals, grants = preflight(manifest, accounts, metadata, users, acls, previous=previous)
        for topic, expected in topics:
            admin("updateTopic", "-t", topic, "-r", str(expected["readQueueNums"]),
                  "-w", str(expected["writeQueueNums"]), "-p", str(expected["perm"]),
                  "-a", "+message.type=" + expected["message_type"], mutation=True)
        for group in groups:
            admin("updateSubGroup", "-g", group, "-q", str(manifest["group_options"]["retry_queue_nums"]), mutation=True)
        for role in principals:
            account = accounts[role]
            admin("createUser", "-u", account["username"], "-p", account["password"], "-t", "Normal", mutation=True)
        for role, resource, actions in grants:
            admin("createAcl", "-s", "User:" + accounts[role]["username"], "-r", resource,
                  "-a", ",".join(sorted(actions)), "-d", "Allow", mutation=True)
        readback = verify_readback(admin, directory, manifest, accounts, previous=previous)
        result = {"version": manifest['version'], "operations": admin.operations, "typed_topics": len(desired_topics(manifest)),
                  "principals": len(manifest.get("accounts", {})), "verified": True, "readback": readback}
        if previous is not None:
            from readable_transition import digest
            result['transition'] = dict(previous_manifest_sha256=digest(previous),
                manifest_sha256=digest(manifest), phase='resources_and_union_acl_prepared',
                credential_rotation=False, retirement_completed=False, business_acceptance=False)
        return result
    except ProvisionReadbackError:
        raise
    except RuntimeError as error:
        # All RuntimeError strings in this module are authored fixed diagnostics;
        # never interpolate captured stdout, credentials or argv here.
        raise RuntimeError("v2 provision: " + str(error)) from None
    except Exception as error:
        raise RuntimeError("v2 provision parser: " + type(error).__name__) from None
    finally:
        # Exactly these two generated metadata files and these owned directories.
        for filename in ("topic.json", "subscriptionGroup.json"):
            admin.docker("rm", "-f", "--", directory + "/" + filename, required=False)
        admin.docker("rmdir", directory, required=False)
        admin.docker("rmdir", lock)
