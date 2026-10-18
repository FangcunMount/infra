"""Version1 canonical logical/physical route bindings, independent of SDKs."""
import hashlib


def physical_topic(topic):
    return "rmq_t_" + hashlib.sha256(topic.encode()).hexdigest()[:32]


def consumer_group(topic, subscription):
    return "rmq_g_" + hashlib.sha256((topic + "\0" + subscription).encode()).hexdigest()[:32]


def validate(manifest):
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
