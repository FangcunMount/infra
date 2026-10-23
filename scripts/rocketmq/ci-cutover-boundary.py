#!/usr/bin/env python3
"""Required owned-process tests; no Docker, SSH or external dependency."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from audit_transaction_limit import write_private


def main():
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    before = subprocess.check_output(['git', 'status', '--porcelain'], text=True)
    output = io.StringIO()
    with tempfile.TemporaryDirectory(prefix='m3-cutover-boundary-') as root:
        os.chmod(root, 0o700)
        # All test fixtures live under this owned directory and clean themselves.
        previous = tempfile.tempdir
        tempfile.tempdir = root
        try:
            loader = unittest.TestLoader()
            suite = unittest.TestSuite(loader.discover('scripts/rocketmq', pattern=pattern)
                                      for pattern in ('test_start_boundary.py', 'test_cutover_step.py'))
            def ids(tests):
                return [name for test in tests for name in
                        (ids(test) if isinstance(test, unittest.TestSuite) else [test.id()])]
            test_ids = ids(suite)
            result = unittest.TextTestRunner(stream=output).run(suite)
            fixture_empty = not any(Path(root).iterdir())
        finally:
            tempfile.tempdir = previous
    after = subprocess.check_output(['git', 'status', '--porcelain'], text=True)
    failed = len(result.errors) + len(result.failures)
    passed = result.testsRun - failed - len(result.skipped)
    clean = before == after == ''
    evidence = {'schema': 'm3-cutover-boundary-process/v1', 'source_sha': source,
                'test_ids': test_ids,
                'passed': passed, 'failed': failed, 'skipped': len(result.skipped),
                'source_clean_before': before == '', 'source_clean_after': after == '',
                'cleanup': {'fixture_empty_before_removal': fixture_empty,
                            'private_fixture_directory_removed': not Path(root).exists()},
                'scope': 'owned_process_and_file_boundary_not_runtime_or_database_acceptance',
                'production_executed': False, 'cutover_authorized': False,
                'harness_sha256': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in (Path(__file__).resolve().relative_to(Path.cwd()),
                                               Path('scripts/rocketmq/start_boundary.py'),
                                               Path('scripts/rocketmq/cutover_step.py'),
                                               Path('scripts/rocketmq/test_start_boundary.py'),
                                               Path('scripts/rocketmq/test_cutover_step.py'))}}
    write_private(Path('cutover-boundary.json'), evidence)
    # Do not print captured command/test exception contents.
    print(json.dumps({'passed': passed, 'failed': failed, 'skipped': len(result.skipped),
                      'cleanup_verified': all(evidence['cleanup'].values())}))
    return 0 if (passed >= 17 and failed == 0 and not result.skipped and clean
                 and all(evidence['cleanup'].values())) else 1


if __name__ == '__main__':
    raise SystemExit(main())
