"""Owned real-Mongo audit instrumentation proof, without application images."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets

from audit_transaction_limit import write_private
from image_start_fixture import require
from mongo_ddl_audit import AuditError, FILTER, KINDS, install, read
from qs_image_pair import QSPairFixture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();require(not args.report.exists(),'new_report_required')
    report=dict(schema='m3-owned-mongo-ddl-audit-proof/v1',passed=0,failed=0,skipped=0,cases={},
        dependency_image_ids={},production=False,application_startup_verified=False)
    f=QSPairFixture(Path(__file__).resolve().parents[2],report)
    network_created=False
    try:
        report['infra_sha']=f.run(['git','rev-parse','HEAD'],cwd=f.repo).stdout.strip()
        f.run(['docker','network','create','--internal','--label',f.label,f.network]);network_created=True
        f.mongo_dependencies();report['cases']['pinned_real_mongo_replica_set']=True
        old='qs_m3_image_start_'+secrets.token_hex(6)
        program='const d=db.getSiblingDB('+json.dumps(old)+');d.setProfilingLevel(2);'
        program+='const rows=d.system.profile.find('+json.dumps(FILTER)+').toArray();'
        program+='print(JSON.stringify(rows.map(r=>{const k='+json.dumps(KINDS)+'.find(k=>Object.hasOwn(r.command,k));return {kind:k,collection:r.command[k]};})));'
        report['original_setup_only_commands']=json.loads(f.mongo(program))
        report['cases']['original_setup_only_projected_readback']=True
        database='qs_m3_image_start_'+secrets.token_hex(6)
        install(f.mongo,database);report['cases']['plain_mongosh_audit_installation']=True
        f.mongo('const d=db.getSiblingDB('+json.dumps(database)+');d.createCollection("actual_ddl_probe");d.actual_ddl_probe.drop();')
        report['audit']=read(f.mongo,database)
        require(report['audit']['attempts']==2 and report['audit']['positive_controls']==4
            and {r['kind'] for r in report['audit']['commands']}=={'create','drop'}
            and all(r['collection']=='actual_ddl_probe' and r['error_code']==0 for r in report['audit']['commands']), 'real_ddl_positive_detection_required')
        report['cases']['real_ddl_detected_with_retained_positive_controls']=True
    except Exception as error:
        report.update(failed=1,failure_kind=type(error).__name__)
        if isinstance(error,AuditError):report['mongo_audit_failure']=error.audit_diagnostic
    finally:
        report['passed']=len(report['cases'])
        try:
            ids=f.run(['docker','ps','-aq','--filter','label='+f.label]).stdout.split()
            if ids:f.run(['docker','rm','-f',*ids])
            if network_created:f.run(['docker','network','rm',f.network])
            f.cleanup()
        except Exception:report['failed']=1
        write_private(args.report,report)
    return int(report['failed']!=0)


if __name__=='__main__':raise SystemExit(main())
