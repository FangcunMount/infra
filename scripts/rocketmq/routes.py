"""Version1 canonical logical/physical route bindings, independent of SDKs."""
import hashlib
import re
import struct


def physical_topic(topic):
    return "rmq_t_" + hashlib.sha256(topic.encode()).hexdigest()[:32]


def consumer_group(topic, subscription):
    return "rmq_g_" + hashlib.sha256((topic + "\0" + subscription).encode()).hexdigest()[:32]


def validate(manifest):
    if manifest.get("version") == 3:
        return validate_v3(manifest)
    if manifest.get("version") == 2:
        return validate_v2(manifest)
    if manifest.get("version") != 1 or not manifest.get("routes"):
        raise ValueError("nonempty version1 route manifest required")
    identities, physical = set(), {}
    for route in manifest["routes"]:
        topic, sub = route["topic"], route.get("subscription", "")
        if not topic or "\0" in topic or "\0" in sub:
            raise ValueError("invalid logical route")
        identity = topic, sub
        if identity in identities:
            raise ValueError("duplicate binding")
        identities.add(identity)
        expected = physical_topic(topic)
        if route["physical_topic"] != expected:
            raise ValueError("noncanonical physical topic")
        if physical.setdefault(expected, topic) != topic:
            raise ValueError("physical collision")
        expected_group = consumer_group(topic, sub) if sub else ""
        if route.get("consumer_group", "") != expected_group:
            raise ValueError("noncanonical group")
    for account in manifest.get("accounts", {}).values():
        topics = {topic for topic, _ in identities}
        if not set(account.get("publish", ())) <= topics:
            raise ValueError("account references unknown publisher route")
        if not {tuple(s) for s in account.get("subscriptions", ())} <= identities:
            raise ValueError("account references unknown subscription")


OWNERS = {"iam.mysql", "qs.mysql", "qs.mongo", "ai.mysql"}


def _field_v2(value, limit):
    if not isinstance(value, str) or not value or "\0" in value or len(value.encode()) > limit:
        raise ValueError("invalid v2 route field")
    return value.encode()


def _digest_v2(domain, fields):
    return hashlib.sha256(domain + b"".join(struct.pack(">Q", len(v)) + v for v in fields)).hexdigest()[:32]


def physical_topic_v2(topic, message_type, owner, revision):
    if message_type not in ("NORMAL", "TRANSACTION"):
        raise ValueError("NORMAL or TRANSACTION route required")
    return "rmq2_t_" + _digest_v2(b"rmq-topic-v2\0", (
        _field_v2(topic, 255), message_type.encode(), _field_v2(owner, 128), _field_v2(revision, 128)))


def consumer_group_v2(topic, subscription):
    return "rmq2_g_" + _digest_v2(b"rmq-group-v2\0", (_field_v2(topic, 255), _field_v2(subscription, 255)))


def validate_v2(manifest, *, readable=False):
    if manifest.get("version") != (3 if readable else 2) or not manifest.get("routes"):
        raise ValueError("nonempty v2 manifest required")
    ids, identities, physical, groups = {}, set(), {}, {}
    for route in manifest["routes"]:
        identity = (route["topic"], route.get("subscription", ""), route["message_type"],
                    route["owner"], route["route_revision"])
        _field_v2(route.get("id"),128)
        if route["id"] in ids or identity in identities:
            raise ValueError("explicit unique route id and binding required")
        ids[route["id"]] = route
        identities.add(identity)
        if route["message_type"] == "TRANSACTION" and route["owner"] not in OWNERS:
            raise ValueError("unreviewed transaction store owner")
        if route.get("naming_scheme", "") != ("readable-v1" if readable else ""):
            raise ValueError("explicit reviewed naming scheme required")
        topic_name = physical_topic_v3 if readable else physical_topic_v2
        group_name = consumer_group_v3 if readable else consumer_group_v2
        expected = topic_name(route["topic"], route["message_type"], route["owner"], route["route_revision"])
        expected_group = group_name(route["topic"], route["subscription"]) if route.get("subscription") else ""
        if route["physical_topic"] != expected or route.get("consumer_group", "") != expected_group:
            raise ValueError("noncanonical v2 physical route or group")
        identity_topic = (route["topic"], route["message_type"], route["owner"], route["route_revision"])
        if physical.setdefault(expected, identity_topic) != identity_topic:
            raise ValueError("physical topic collision")
        if expected_group and groups.setdefault(expected_group, (route["topic"], route["subscription"])) != (route["topic"], route["subscription"]):
            raise ValueError("consumer group collision")
    for role, grants in manifest.get("accounts", {}).items():
        if role in ("admin", "inner") or not role:
            raise ValueError("application role required")
        publishers, subscribers = grants.get("publish", []), grants.get("subscriptions", [])
        if (set(grants) - {"owner","publish","subscriptions"} or not isinstance(publishers,list)
            or not isinstance(subscribers,list) or not (publishers or subscribers)
            or any(not isinstance(value,str) for value in publishers+subscribers)
            or len(set(publishers))!=len(publishers) or len(set(subscribers))!=len(subscribers)):
            raise ValueError("explicit distinct publish/subscription route grants required")
        if not set(publishers + subscribers) <= ids.keys():
            raise ValueError("account refers to unknown route id")
        if publishers and (not grants.get("owner") or any(ids[r]["owner"] != grants["owner"] for r in publishers)):
            raise ValueError("publisher grants cross transaction owner boundary")
        if any(not ids[r].get("subscription") for r in subscribers):
            raise ValueError("subscription route required")
    options = manifest.get("topic_options", {})
    if set(options) != {"read_queue_nums", "write_queue_nums", "perm"} or not all(type(options[k]) is int and 1 <= options[k] <= 64 for k in ("read_queue_nums", "write_queue_nums")) or options["perm"] != 6:
        raise ValueError("explicit bounded topic queues and read/write permission required")
    groups = manifest.get("group_options", {})
    if set(groups) != {"retry_queue_nums"} or type(groups["retry_queue_nums"]) is not int or not 1 <= groups["retry_queue_nums"] <= 128:
        raise ValueError("explicit bounded retry queues required")


def _readable_field(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", value):
        raise ValueError("readable fields require lowercase single-separated tokens")
    return value.replace(".", "-")


def _readable_name(*fields):
    name = "--".join(_readable_field(v) for v in fields)
    if len(name.encode()) > 64:
        raise ValueError("readable resource exceeds 64 bytes")
    return name


def physical_topic_v3(topic, message_type, owner, revision):
    if message_type not in ("NORMAL", "TRANSACTION"):
        raise ValueError("NORMAL or TRANSACTION required")
    return _readable_name(topic, "normal" if message_type == "NORMAL" else "tx", owner, revision)


def consumer_group_v3(topic, subscription):
    return _readable_name(topic, subscription)


def validate_v3(manifest):
    validate_v2(manifest, readable=True)
    history = manifest.get("historical_routes", [])
    if not isinstance(history, list):
        raise ValueError("historical route list required")
    if history:
        validate_v2({**manifest, "version": 2, "routes": history, "accounts": {}})
        for field in ("physical_topic", "consumer_group"):
            current = {r[field] for r in manifest["routes"] if r.get(field)}
            previous = {r[field] for r in history if r.get(field)}
            if current & previous:
                raise ValueError("active and historical resources overlap")


def permissions_v2(manifest, grants):
    routes = {route["id"]: route for route in manifest["routes"]}
    permissions = {}
    for identity in grants.get("publish", []):
        route = routes[identity]
        permissions.setdefault("Topic:" + route["physical_topic"], set()).update(("Pub", "Get"))
    for identity in grants.get("subscriptions", []):
        route = routes[identity]
        permissions.setdefault("Topic:" + route["physical_topic"], set()).update(("Sub", "Get"))
        permissions.setdefault("Group:" + route["consumer_group"], set()).update(("Sub", "Get"))
    return permissions
