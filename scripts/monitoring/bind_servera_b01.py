"""Prepare the reviewed source input before the H03 decision is signed."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

from verify_b01_b05 import match_source, paired_originals, read, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--b01", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source, _ = read(args.source)
    b01, digest = read(args.b01)
    require(
        b01["schema"] == "monitoring-h03-b01-capture/v1"
        and b01["operation_id"] == args.operation_id
        and b01["eligible_for_review"] is True
        and b01["execution_authorized"] is False
        and b01["capture_exit"] == {"macmini": 0, "candidate": 0},
        "expected an eligible B01 receipt for the requested operation",
    )
    old = paired_originals(args.b01.parent, b01)
    match_source(source, old)
    require(
        "b01_overlap_receipt_sha256" not in source,
        "expected the original H03 source capture",
    )
    source["b01_overlap_receipt_sha256"] = digest
    raw = (json.dumps(source, indent=2) + "\n").encode()
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(args.out.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    print(
        json.dumps(
            dict(
                operation_id=args.operation_id,
                source_sha256=sha256(raw).hexdigest(),
                b01_overlap_receipt_sha256=digest,
                execution_authorized=False,
            )
        )
    )


if __name__ == "__main__":
    main()
