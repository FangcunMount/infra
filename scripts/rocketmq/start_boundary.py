"""Persistent first-runtime boundary for one approved, fixed operation location.

Callbacks are supplied by the reviewed cutover adapter; this module never selects
hosts, runs a shell, changes a provider, restores data or retries business work.
All starts/restores in the approved window must use the same location and host
deployment locks. Missing evidence or out-of-band starts invalidate eligibility.
"""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid


class BoundaryError(RuntimeError):
    pass


def _json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise BoundaryError('duplicate operation field')
            out[key] = value
        return out
    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise BoundaryError('operation object required')
    return value


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def _digest(value):
    if not isinstance(value, str) or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise BoundaryError('independent exact digest required')
    return value


def _step(value):
    if not isinstance(value, str) or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value) is None:
        raise BoundaryError('bounded frozen step identity required')
    return value


def _read(fd, name):
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(child, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1 or info.st_uid != os.geteuid() or info.st_size > 16384):
            raise BoundaryError('private bounded operation evidence required')
        raw = stream.read(16385)
    if len(raw) > 16384:
        raise BoundaryError('operation evidence exceeds limit')
    return raw


def _publish(fd, name, value, *, replace=False):
    # The directory lock excludes concurrent writers. Never overwrite a barrier.
    temp = '.next-' + uuid.uuid4().hex if replace else name
    child = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(child, 'wb') as stream:
            stream.write(_encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.rename(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    except BaseException:
        if replace:
            with contextlib.suppress(OSError):
                os.unlink(temp, dir_fd=fd)
        raise


def initialize(directory, binding, reviewed_sha256):
    """Create once; never repair, reset or replace an existing operation."""
    directory = Path(directory)
    raw = _encoded(binding)
    if hashlib.sha256(raw).hexdigest() != _digest(reviewed_sha256):
        raise BoundaryError('reviewed operation binding differs')
    expected = {'schema', 'operation_id', 'directory', 'scope_sha256', 'protection_sha256',
                'restore_receipt_sha256', 'source_bundle_sha256', 'data_owner', 'recovery_owner'}
    if set(binding) != expected or binding['schema'] != 'm3-start-boundary/v1':
        raise BoundaryError('exact operation binding required')
    if not isinstance(binding['operation_id'], str) or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', binding['operation_id']) is None:
        raise BoundaryError('bounded operation identity required')
    if not directory.is_absolute() or str(directory) != binding['directory']:
        raise BoundaryError('reviewed operation location differs')
    for key in ('scope_sha256', 'protection_sha256', 'restore_receipt_sha256', 'source_bundle_sha256'):
        _digest(binding[key])
    for key in ('data_owner', 'recovery_owner'):
        if (not isinstance(binding[key], str) or not binding[key].strip()
                or len(binding[key].encode()) > 128 or any(ord(c) < 32 for c in binding[key])):
            raise BoundaryError('named operation responsibility required')
    directory.mkdir(mode=0o700, exist_ok=False)
    os.chmod(directory, 0o700)
    with Boundary(directory, reviewed_sha256, initializing=True) as operation:
        _publish(operation.fd, 'binding.json', binding)
        _publish(operation.fd, 'state.json', {'binding_sha256': reviewed_sha256, 'phase': 'initialized', 'step': ''})
        parent = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)


class Boundary:
    def __init__(self, directory, reviewed_sha256, *, initializing=False):
        self.directory = Path(directory)
        self.digest = _digest(reviewed_sha256)
        self.initializing = initializing
        self.fd = None

    def __enter__(self):
        self.fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(self.fd)
            if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
                raise BoundaryError('fixed private operation directory required')
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self.initializing:
                binding = _read(self.fd, 'binding.json')
                if hashlib.sha256(binding).hexdigest() != self.digest:
                    raise BoundaryError('immutable operation binding differs')
                if _json(binding).get('directory') != str(self.directory):
                    raise BoundaryError('operation cannot move to another location')
                self._state()
            return self
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def __exit__(self, *unused):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _started(self):
        try:
            os.stat('first-runtime-start.json', dir_fd=self.fd, follow_symlinks=False)
            return True  # Even a corrupt/partial marker forbids old-data restore.
        except FileNotFoundError:
            return False

    def _state(self):
        value = _json(_read(self.fd, 'state.json'))
        phases = {'initialized', 'runtime_start_issued', 'runtime_start_returned', 'runtime_start_failed',
                  'maintenance_issued', 'maintenance_returned', 'maintenance_failed',
                  'restore_issued', 'restore_returned', 'restore_failed',
                  'forward_repair_issued', 'forward_repair_returned', 'forward_repair_failed'}
        if (set(value) != {'binding_sha256', 'phase', 'step'} or value['binding_sha256'] != self.digest
                or not isinstance(value['phase'], str) or value['phase'] not in phases
                or not isinstance(value['step'], str)):
            raise BoundaryError('operation state is incomplete or inconsistent')
        if value['phase'].startswith(('runtime_', 'forward_')) and not self._started():
            raise BoundaryError('start history without its persistent barrier')
        return value

    def _record(self, phase, step):
        _step(step)
        _publish(self.fd, 'state.json', {'binding_sha256': self.digest, 'phase': phase, 'step': step}, replace=True)

    def status(self):
        state = self._state()
        return {'phase': state['phase'], 'runtime_may_have_started': self._started(),
                'old_data_restore_eligible': not self._started() and state['phase'] in
                {'initialized', 'maintenance_issued', 'maintenance_returned', 'maintenance_failed',
                 'restore_issued', 'restore_failed'}, 'cutover_authorized': False}

    def start(self, step, callback):
        _step(step)
        state = self._state()
        if state['phase'] not in {'initialized', 'maintenance_returned', 'runtime_start_returned', 'forward_repair_returned'}:
            raise BoundaryError('failed or unknown start requires forward repair')
        if state['phase'] in {'initialized', 'maintenance_returned'} and self._started():
            raise BoundaryError('interrupted start publication requires forward repair')
        if not self._started():
            _publish(self.fd, 'first-runtime-start.json', {'binding_sha256': self.digest, 'first_step': step})
        self._record('runtime_start_issued', step)  # Durable BEFORE callback/command.
        try:
            result = callback()
        except BaseException:
            self._record('runtime_start_failed', step)
            raise
        self._record('runtime_start_returned', step)
        return result

    def restore_before_start(self, step, callback):
        _step(step)
        state = self._state()
        if self._started() or state['phase'] not in {'initialized', 'maintenance_issued', 'maintenance_returned',
                                                   'maintenance_failed', 'restore_issued', 'restore_failed'}:
            raise BoundaryError('old-data restore forbidden after any runtime start attempt')
        self._record('restore_issued', step)  # Also closes normal start, including failed restores.
        try:
            result = callback()
        except BaseException:
            self._record('restore_failed', step)
            raise
        self._record('restore_returned', step)
        return result

    def maintain_before_start(self, step, callback, repair_approval_sha256=None):
        """Guard an explicit offline step, never migrate or install implicitly.

        Failure/exit is not proof that remote DDL stopped. The reviewed repair or
        restore script must verify actual database activity before doing work.
        """
        _step(step)
        state = self._state()
        if self._started():
            raise BoundaryError('pre-start maintenance forbidden after runtime start attempt')
        if repair_approval_sha256 is None:
            if state['phase'] not in {'initialized', 'maintenance_returned'}:
                raise BoundaryError('failed or unknown maintenance requires separate repair')
        else:
            _digest(repair_approval_sha256)
            if state['phase'] not in {'maintenance_issued', 'maintenance_failed'}:
                raise BoundaryError('pre-start repair requires failed or unknown maintenance')
            try:
                _publish(self.fd, 'prestart-repair-approval-' + repair_approval_sha256 + '.json',
                         {'binding_sha256': self.digest, 'step': step, 'approval_sha256': repair_approval_sha256})
            except FileExistsError:
                raise BoundaryError('pre-start repair approval already consumed') from None
        self._record('maintenance_issued', step)
        try:
            result = callback()
        except BaseException:
            self._record('maintenance_failed', step)
            raise
        self._record('maintenance_returned', step)
        return result

    def forward_repair(self, step, approval_sha256, callback):
        _step(step)
        _digest(approval_sha256)
        self._state()
        if not self._started():
            raise BoundaryError('forward repair requires existing start responsibility')
        receipt = {'binding_sha256': self.digest, 'step': step, 'approval_sha256': approval_sha256}
        name = 'repair-approval-' + approval_sha256 + '.json'
        try:
            _publish(self.fd, name, receipt)
        except FileExistsError:
            if _read(self.fd, name) != _encoded(receipt):
                raise BoundaryError('repair approval cannot change its binding') from None
        # The reviewed adapter binds the separate repair approval to its exact
        # compatible image/commands; this guard never executes an old backup.
        self._record('forward_repair_issued', step)
        try:
            result = callback()
        except BaseException:
            self._record('forward_repair_failed', step)
            raise
        self._record('forward_repair_returned', step)
        return result
