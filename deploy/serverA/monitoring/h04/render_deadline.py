"""Translate the signed UTC cutoff to ServerD OpenSSH 8.9's local expiry syntax."""
from datetime import datetime, timedelta, timezone
import json
import re
import sys
from zoneinfo import ZoneInfo


def render(cutoff, host_zone):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cutoff):
        raise ValueError("approved cutoff must be a whole second in UTC ending in Z")
    if host_zone != "Asia/Shanghai":
        raise ValueError("ServerD timezone drift requires requalification")
    signed = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    zone = ZoneInfo(host_zone)
    # OpenSSH 8.9 authenticates throughout the emitted expiry second.
    last_allowed = signed - timedelta(seconds=1)
    field = last_allowed.astimezone(zone).strftime("%Y%m%d%H%M%S")
    interpreted = datetime.strptime(field, "%Y%m%d%H%M%S").replace(tzinfo=zone)
    if interpreted.astimezone(timezone.utc) != last_allowed:
        raise ValueError("ambiguous ServerD local time")
    return {
        "approval_cutoff_utc": cutoff,
        "server_timezone": host_zone,
        "sshd_expiry_time": field,
        "sshd_last_accepted_clock_second_utc": last_allowed.isoformat(),
        "withdrawal_calendar_utc": signed.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "execution_authorized": False,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: render-deadline.py YYYY-MM-DDTHH:MM:SSZ Asia/Shanghai")
    print(json.dumps(render(*sys.argv[1:]), indent=2))
