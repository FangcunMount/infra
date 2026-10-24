"""Synthetic producer fixture only; no database, approval or runtime authority."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_transaction_limit import write_private
from image_cutover_offline import offline_approval, offline_operation_id
from qs_image_pair import QS_SHA

value = offline_approval(dict(source_sha=QS_SHA, migration_resources_sha256='b'*64,
    mysql_database='qs_m3_image_contract', mongo_database='qs_m3_image_contract',
    mysql_identity_sha256='c'*64, mongo_cluster_sha256='d'*64),
    operation_id=offline_operation_id(os.environ), started=datetime.now(timezone.utc)-timedelta(seconds=2),
    protection=SimpleNamespace(manifest_sha='1'*64, receipt_sha='2'*64, restore_seconds=5,
        f=SimpleNamespace(directory=Path('/tmp/m3-owned-contract'))),
    startup_sha='3'*64, scope_sha='4'*64, responsibility_sha='5'*64)
write_private(Path(sys.argv[1]), value)
