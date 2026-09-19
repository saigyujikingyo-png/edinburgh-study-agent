"""Bounded, account-scoped supervision for the existing private Work connector.

The scheduled-task PowerShell file is only a launch shim. This module owns the
supervision policy; Windows is an adapter, not a second implementation.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


class LifecycleError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical(path):
    value = Path(path).absolute()
    for parent in (value, *value.parents):
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400):
            raise LifecycleError('REPARSE_POINT')
    return os.path.normcase(str(value.resolve()))


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    executable: str
    born: str
    argv: tuple[str, ...]

    def record(self):
        return dict(pid=self.pid, parent=self.parent, executable=self.executable,
                    born=self.born, argv=list(self.argv))


def argument(argv, name):
    positions = [i for i, item in enumerate(argv) if item == name]
    if len(positions) != 1 or positions[0] + 1 >= len(argv):
        return None
    return argv[positions[0] + 1]


@dataclass(frozen=True)
class Profile:
    directory: Path
    home: Path
    alias: str
    profile_directory: str
    client: str
    python: str
    secret_file: Path
    task_name: str

    @property
    def scope(self):
        return hashlib.sha256((self.alias.casefold() + '\n' + canonical(self.profile_directory)).encode()).hexdigest()

    @property
    def state_path(self):
        return self.directory / 'lifecycle-status.json'

    def same_path(self, observed, expected):
        try:
            return bool(observed) and canonical(observed) == canonical(expected)
        except (LifecycleError, OSError, ValueError):
            return False

    def daemon(self, p):
        return (self.same_path(p.executable, self.client)
                and argument(p.argv, '--profile') == self.alias
                and self.same_path(argument(p.argv, '--profile-dir'), self.profile_directory))

    def server(self, p):
        # The release bundle embeds Python directly. A development venv may use
        # one CPython redirector; only its declared base executable is accepted.
        executables = [self.python]
        cfg = self.home/'runtime/pyvenv.cfg'
        if cfg.is_file():
            canonical(cfg)
            values = dict(line.split('=', 1) for line in cfg.read_text().splitlines() if '=' in line)
            values = {k.strip(): v.strip() for k, v in values.items()}
            if values.get('executable'):
                executables.append(values['executable'])
            elif values.get('home'):
                executables.append(str(Path(values['home'])/'python.exe'))
        return (any(self.same_path(p.executable, exe) for exe in executables)
                and p.argv[1:3] == ('-m', 'edinburgh_study_agent.server'))

    def child(self, p, parent):
        return p.parent == parent.pid and p.born >= parent.born and self.server(p)

    def supervisor(self, p):
        return (self.same_path(p.executable, self.python)
                and p.argv[1:4] == ('-m', 'edinburgh_study_agent.work_runtime', 'run')
                and self.same_path(argument(p.argv, '--connection-directory'), self.directory))


    def wrapper(self, p):
        shell = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
        return (self.same_path(p.executable, shell) and len(p.argv) == 9
                and tuple(a.casefold() for a in p.argv[1:8]) ==
                    ('-noprofile','-noninteractive','-windowstyle','hidden','-executionpolicy','bypass','-file')
                and self.same_path(p.argv[8], self.directory/'Run-Work-Connection.ps1'))


def load_profile(directory):
    from .work_profiles import inspect_profile
    value = inspect_profile(Path(directory))
    return Profile(**{key: value[key] for key in Profile.__dataclass_fields__})


@contextmanager
def ownership_lock(profile, timeout=0):
    """Cross-process and cross-logon-session lock; a stale file is harmless."""
    root = Path(profile.profile_directory)
    root.mkdir(parents=True, exist_ok=True)
    canonical(root)
    lock_path = root / ('uoe-' + profile.scope + '.lock')
    canonical(lock_path)
    handle = lock_path.open('a+b')
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise LifecycleError('OWNER_BUSY') from None
                time.sleep(.1)
        yield
    finally:
        if acquired:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class Supervisor:
    def __init__(self, profile, backend, *, command_seconds=10, readiness_seconds=30,
                 health_seconds=30, retries=(5, 15, 30)):
        self.p, self.b = profile, backend
        self.command_seconds, self.readiness_seconds = command_seconds, readiness_seconds
        self.health_seconds, self.retries = health_seconds, retries
        self.known = {}
        self.attempt = 0
        self.daemon = None
        self._load_owned()

    def _load_owned(self):
        if not self.p.state_path.exists():
            return
        try:
            canonical(self.p.state_path)
            if self.p.state_path.stat().st_size > 131072:
                raise ValueError()
            data = json.loads(self.p.state_path.read_text(encoding='utf-8'))
            if data.get('scope') != self.p.scope:
                raise ValueError()
            for row in data.get('owned', []):
                row['argv'] = tuple(row['argv'])
                item = Process(**row)
                if not isinstance(item.pid, int) or not item.born or not item.executable:
                    raise ValueError()
                self.known[item.pid] = item
            proved = {pid: item for pid,item in self.known.items() if self.p.daemon(item)}
            for _ in range(3):
                proved.update({pid:item for pid,item in self.known.items()
                               if any(self.p.child(item,parent) for parent in list(proved.values()))})
            if len(proved) != len(self.known):
                raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise LifecycleError('INVALID_OWNERSHIP_RECEIPT') from None

    def receipt(self, state, *, ready=False, error=None):
        now = self.b.wall_time()
        value = dict(schema_version=1, scope=self.p.scope, state=state,
                     checked_at=now, valid_for_seconds=self.health_seconds + 2*self.command_seconds,
                     ready=ready, healthy=ready, process_running=self.daemon is not None,
                     pid=self.daemon.pid if self.daemon else None,
                     supervisor_pid=self.b.self_pid(), recovery_attempt=self.attempt,
                     verification_scope='local_transport_only', error_code=error,
                     owned=[p.record() for p in self.known.values()])
        for name in ('lifecycle-status.json', 'status.json', 'error.json'):
            canonical(self.p.directory/name)
        atomic_json(self.p.state_path, value)
        public = {k: v for k, v in value.items() if k != 'owned'}
        atomic_json(self.p.directory / 'status.json', public)
        # Resolve old errors explicitly instead of allowing contradictory receipts.
        atomic_json(self.p.directory / 'error.json', {**public, 'resolved': error is None})
        return public

    def snapshot(self, deadline=None):
        timeout = 10 if deadline is None else min(10, deadline-self.b.monotonic())
        if timeout <= 0:
            raise LifecycleError('READINESS_TIMEOUT')
        rows = self.b.processes(timeout=timeout)
        daemons = [p for p in rows if self.p.daemon(p)]
        current = {p.pid: p for p in rows}
        # Only observe new lineage while the exact parent is present. Previously
        # proved children may survive it, but a stale parent PID cannot adopt a
        # newly discovered orphan. Preserve those candidates as unknown.
        for daemon in daemons:
            self.known[daemon.pid] = daemon
        parents = [p for p in self.known.values() if current.get(p.pid) == p]
        for _ in range(3):
            added = []
            for p in rows:
                if p.pid not in self.known and any(self.p.child(p, parent) for parent in parents):
                    self.known[p.pid] = p
                    added.append(p)
            if not added:
                break
            parents = added
        valid = {pid: old for pid, old in self.known.items() if current.get(pid) == old}
        return rows, daemons, valid

    def external_frontend(self, process, rows):
        """Exclusion requires a live, older parent chain, not absence of a receipt.

        An ordinary host may own a frontend through a Python redirector. Traverse
        those server nodes until the live non-transport parent is proved. Missing,
        inaccessible or recycled parents remain unknown, including first startup
        after a crash before any daemon/child receipt could be persisted.
        """
        current={p.pid:p for p in rows}
        visited={process.pid}
        for _ in range(8):
            parent=current.get(process.parent)
            if parent is None or parent.pid in visited or parent.born > process.born:
                return False
            visited.add(parent.pid)
            if self.p.server(parent):
                process=parent
                continue
            if self.p.wrapper(parent) or self.p.supervisor(parent):
                return False
            alias=argument(parent.argv,'--profile')
            directory=argument(parent.argv,'--profile-dir')
            if alias is not None or directory is not None or self.p.same_path(parent.executable,self.p.client):
                return (alias is not None and alias != self.p.alias and directory is not None
                        and not self.p.same_path(directory,self.p.profile_directory))
            # Another incomplete UoE Python ownership chain is not host evidence.
            if argument(parent.argv,'-m') in ('edinburgh_study_agent.server','edinburgh_study_agent.work_runtime'):
                return False
            return True
        return False

    def unresolved_children(self, rows, proven):
        return [p for p in rows if self.p.server(p) and p.pid not in proven
                and not self.external_frontend(p, rows)]

    def child_chain(self, rows, owner, proven):
        if self.unresolved_children(rows, proven):
            raise LifecycleError('ORPHAN_OWNERSHIP_UNKNOWN')
        chain, parent = [], owner
        for _ in range(3):
            children = [p for p in rows if self.p.child(p, parent)]
            if len(children) > 1:
                raise LifecycleError('COMPETING_CHILDREN')
            if not children:
                break
            chain.extend(children)
            parent = children[0]
        if len(chain) > 2 or any(self.p.server(p) and p not in chain for p in proven.values()):
            raise LifecycleError('COMPETING_CHILDREN')
        return chain

    def probe(self, deadline=None):
        timeout = self.command_seconds
        if deadline is not None:
            timeout = min(timeout, deadline - self.b.monotonic())
        if timeout <= 0:
            raise LifecycleError('READINESS_TIMEOUT')
        result = self.b.client(['runtimes', 'status', self.p.alias, '--json'], timeout)
        if result['code'] != 0:
            raise LifecycleError('STATUS_FAILED')
        try:
            data = json.loads(result['stdout'])
            if not isinstance(data, dict) or any(type(data.get(k)) is not bool
                    for k in ('process_running', 'healthy', 'ready')):
                raise ValueError()
        except (ValueError, TypeError):
            raise LifecycleError('STATUS_INVALID') from None
        rows, owners, proven = self.snapshot(deadline)
        if deadline is not None and self.b.monotonic() >= deadline:
            raise LifecycleError("READINESS_TIMEOUT")
        if len(owners) > 1:
            raise LifecycleError('COMPETING_OWNERS')
        reported = data.get('process', {}).get('pid') if isinstance(data.get('process'), dict) else None
        if data['process_running']:
            if len(owners) != 1 or reported != owners[0].pid:
                raise LifecycleError('OWNERSHIP_UNKNOWN')
            if self.daemon and owners[0] != self.daemon:
                raise LifecycleError('OWNER_CHANGED')
            self.daemon = owners[0]
        elif reported and any(p.pid == reported for p in rows):
            raise LifecycleError('OWNERSHIP_UNKNOWN')
        if self.unresolved_children(rows, proven):
            raise LifecycleError('ORPHAN_OWNERSHIP_UNKNOWN')
        chain = self.child_chain(rows, owners[0], proven) if owners else []
        return bool(data['process_running'] and data['healthy'] and data['ready'] and chain)

    def cleanup(self):
        deadline = self.b.monotonic() + 45
        def remaining():
            seconds = min(self.command_seconds, deadline-self.b.monotonic())
            if seconds <= 0:
                raise LifecycleError('CLEANUP_UNCONFIRMED')
            return seconds
        rows, owners, proven = self.snapshot(deadline)
        if self.unresolved_children(rows, proven):
            raise LifecycleError('ORPHAN_OWNERSHIP_UNKNOWN')
        try:
            raw = self.b.client(['runtimes', 'status', self.p.alias, '--json'], remaining())
            registry = json.loads(raw['stdout']) if raw['code'] == 0 else None
        except (LifecycleError, ValueError, TypeError):
            registry = None
        process = registry.get('process') if isinstance(registry, dict) else None
        pid = process.get('pid') if isinstance(process, dict) else None
        # A registry stop is optional, and must never target a foreign live PID.
        if pid and any(p.pid == pid and pid not in proven for p in rows):
            raise LifecycleError('OWNERSHIP_UNKNOWN')
        if isinstance(registry, dict) and isinstance(process, (dict, type(None))):
            try:
                self.b.client(['runtimes', 'stop', self.p.alias], remaining())
            except LifecycleError:
                pass
        # Refresh after registry stop: a producer might have spawned meanwhile.
        # Quiesce producers before descendants, refreshing observed lineage at
        # every boundary. Newly discovered orphans cannot be proved and block
        # all reconnects; unrelated host frontends are never adopted or killed.
        for _ in range(8):
            rows, owners, proven = self.snapshot(deadline)
            if self.unresolved_children(rows, proven):
                raise LifecycleError('ORPHAN_OWNERSHIP_UNKNOWN')
            if not proven:
                self.daemon, self.known = None, {}
                return
            roots = [p for p in proven.values() if p.parent not in proven]
            if not roots:
                raise LifecycleError('CLEANUP_UNCONFIRMED')
            target = min(roots, key=lambda p: p.born)
            self.receipt('stopping')  # Keep lineage if this supervisor dies next.
            current = self.b.process(target.pid, timeout=remaining())
            if current is not None and current != target:
                raise LifecycleError('OWNER_CHANGED')
            if current == target:
                self.b.terminate(target, timeout=remaining())
        raise LifecycleError('CLEANUP_UNCONFIRMED')

    def registry_absent(self, deadline):
        remaining = min(self.command_seconds, deadline-self.b.monotonic())
        if remaining <= 0:
            raise LifecycleError('READINESS_TIMEOUT')
        raw = self.b.client(['runtimes', 'list', '--json'], remaining)
        try:
            aliases = json.loads(raw['stdout'])['aliases']
            if raw['code'] or not isinstance(aliases, list) or any(
                    not isinstance(row, dict) or not isinstance(row.get('alias'), str) for row in aliases):
                raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise LifecycleError('REGISTRY_UNKNOWN') from None
        return not any(row['alias'].casefold() == self.p.alias.casefold() for row in aliases)

    def connect(self):
        deadline = self.b.monotonic() + self.readiness_seconds
        rows, owners, proven = self.snapshot(deadline)
        if self.unresolved_children(rows, proven):
            raise LifecycleError('ORPHAN_OWNERSHIP_UNKNOWN')
        if len(owners) > 1:
            raise LifecycleError('COMPETING_OWNERS')
        if owners:
            self.daemon = owners[0]
            self.receipt('starting')
        else:
            try:
                self.probe(deadline)
            except LifecycleError as error:
                # Official CLI returns nonzero for a never-created alias. Only
                # a successful structured local directory can prove absence.
                if error.code != 'STATUS_FAILED' or not self.registry_absent(deadline):
                    raise
            # Reconcile retained exact-identity orphan children before spawning.
            if proven:
                self.cleanup()
            if self.b.monotonic() >= deadline:
                raise LifecycleError('READINESS_TIMEOUT')
            self.receipt('spawning')  # connect may create a daemon even if it fails.
            env = {'CONTROL_PLANE_API_KEY': self.b.secret(self.p.secret_file), 'PYTHONUTF8': '1'}
            command = subprocess.list2cmdline([self.p.python, '-m', 'edinburgh_study_agent.server'])
            try:
                result = self.b.client(['runtimes', 'connect', '--json', '--alias', self.p.alias,
                    '--profile', self.p.alias, '--profile-dir', self.p.profile_directory,
                    '--tunnel-id', self.b.tunnel_id(), '--mcp-command', command,
                    '--runtime-api-key', 'env:CONTROL_PLANE_API_KEY'],
                    min(self.command_seconds, deadline-self.b.monotonic()), env=env)
            finally:
                env.clear()
            if result['code'] != 0:
                raise LifecycleError('CONNECT_FAILED')
        while True:
            if self.probe(deadline):
                return self.receipt('ready', ready=True)
            self.receipt('starting')
            remaining = deadline - self.b.monotonic()
            if remaining <= 0:
                raise LifecycleError('READINESS_TIMEOUT')
            self.b.sleep(min(1, remaining))

    def run(self, once=False):
        failures = 0
        while True:
            self.attempt = failures
            try:
                result = self.connect()
                if once:
                    return result
                ready_since = self.b.monotonic()
                while True:
                    self.b.sleep(self.health_seconds)
                    # Every observation is new; PID existence is not health.
                    if not self.probe(self.b.monotonic() + 2*self.command_seconds):
                        raise LifecycleError('UNHEALTHY')
                    self.receipt('ready', ready=True)
                    if self.b.monotonic() - ready_since >= 300:
                        failures = 0
            except LifecycleError as exc:
                self.receipt('unhealthy', error=exc.code)
                if exc.code in ('COMPETING_OWNERS', 'COMPETING_CHILDREN', 'ORPHAN_OWNERSHIP_UNKNOWN',
                                'OWNERSHIP_UNKNOWN', 'OWNER_CHANGED', 'COMMAND_CLEANUP_UNKNOWN'):
                    raise
                try:
                    self.cleanup()
                except LifecycleError as cleanup:
                    self.receipt('unknown', error=cleanup.code)
                    raise
                failures += 1
                self.receipt('dead', error=exc.code)
                if once or failures > len(self.retries):
                    raise
                self.b.sleep(self.retries[failures-1])
            except (OSError, ValueError, KeyError, TypeError):
                self.receipt('unknown', error='LOCAL_STATE_UNAVAILABLE')
                raise LifecycleError('LOCAL_STATE_UNAVAILABLE') from None

    def stop(self):
        try:
            self.cleanup()
        except LifecycleError as error:
            self.receipt('unknown', error=error.code)
            raise
        return self.receipt('stopped')


class WindowsBackend:
    """All external commands are fixed programs with argument arrays and deadlines."""
    def __init__(self, profile):
        if os.name != 'nt':
            raise LifecycleError('WINDOWS_REQUIRED')
        self.p = profile
        self.powershell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')

    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)
    self_pid = staticmethod(os.getpid)

    @staticmethod
    def wall_time():
        return datetime.now(timezone.utc).isoformat()

    def command(self, args, timeout, *, env=None, input_text=None):
        if not 0 < timeout <= 60:
            raise LifecycleError('INVALID_DEADLINE')
        try:
            child = subprocess.Popen(args, stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', errors='replace',
                env={**os.environ, **(env or {})}, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            raise LifecycleError('COMMAND_START_FAILED') from None
        try:
            stdout, stderr = child.communicate(input=input_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            # This handle belongs to the exact CLI process we just created.
            # Detached daemons are reconciled separately by the supervisor.
            try:
                child.kill()
            except OSError:
                raise LifecycleError('COMMAND_CLEANUP_UNKNOWN') from None
            try:
                child.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                raise LifecycleError('COMMAND_CLEANUP_UNKNOWN') from None
            raise LifecycleError('COMMAND_TIMEOUT') from None
        if len(stdout) > 2_000_000 or len(stderr) > 100_000:
            raise LifecycleError('COMMAND_OUTPUT_LIMIT')
        return {'code': child.returncode, 'stdout': stdout}

    def client(self, args, timeout, *, env=None):
        return self.command([self.p.client, *args], timeout, env=env)

    def ps(self, script, payload=None, timeout=10):
        preamble = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); "
        if payload is not None:
            preamble += "$request=[Console]::In.ReadToEnd()|ConvertFrom-Json; "
        result = self.command([self.powershell, '-NoProfile', '-NonInteractive', '-Command', preamble+script],
                              timeout, input_text=json.dumps(payload) if payload is not None else None,
                              env={'PSModulePath': str(Path(self.powershell).parent/'Modules')})
        if result['code']:
            raise LifecycleError('WINDOWS_QUERY_FAILED')
        try:
            return json.loads(result['stdout']) if result['stdout'].strip() else None
        except ValueError:
            raise LifecycleError('WINDOWS_QUERY_INVALID') from None

    def processes(self, timeout=10):
        data = self.ps("@(Get-CimInstance Win32_Process|Select-Object ProcessId,ParentProcessId,ExecutablePath,@{Name='CreationDate';Expression={$_.CreationDate.ToUniversalTime().ToString('o')}},CommandLine)|ConvertTo-Json -Depth 3 -Compress", timeout=timeout) or []
        if isinstance(data, dict):
            data = [data]
        return [Process(int(p['ProcessId']), int(p['ParentProcessId']), p['ExecutablePath'],
                        p['CreationDate'], tuple(self._argv(p['CommandLine'])))
                for p in data if p.get('ExecutablePath') and p.get('CommandLine') and p.get('CreationDate')]

    def process(self, pid, timeout=10):
        return next((p for p in self.processes(timeout=timeout) if p.pid == pid), None)

    @staticmethod
    def _argv(value):
        import ctypes
        count = ctypes.c_int()
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        pointer = shell.CommandLineToArgvW(value, ctypes.byref(count))
        if not pointer:
            raise LifecycleError('COMMAND_LINE_UNREADABLE')
        try:
            return [pointer[i] for i in range(count.value)]
        finally:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree.restype = ctypes.c_void_p
            kernel.LocalFree(pointer)

    def terminate(self, expected, timeout=10):
        # One native process handle binds the kill to its creation identity,
        # avoiding a gap between a PID recheck and Stop-Process.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateProcess.restype = wintypes.BOOL
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)]*4)]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000 | 1 | 0x100000, False, expected.pid)
        if not handle:
            if self.process(expected.pid, timeout=timeout) is None:
                return
            raise LifecycleError('CLEANUP_ACCESS_DENIED')
        try:
            from datetime import timedelta
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                raise LifecycleError('CLEANUP_ACCESS_DENIED')
            micros = ((times[0].dwHighDateTime << 32) | times[0].dwLowDateTime)//10
            born = datetime(1601,1,1,tzinfo=timezone.utc) + timedelta(microseconds=micros)
            if born != datetime.fromisoformat(expected.born) or self.process(expected.pid, timeout=timeout) != expected:
                raise LifecycleError('OWNER_CHANGED')
            if not kernel.TerminateProcess(handle, 1):
                raise LifecycleError('CLEANUP_FAILED')
            if kernel.WaitForSingleObject(handle, 2000) != 0:
                raise LifecycleError('CLEANUP_UNCONFIRMED')
        finally:
            kernel.CloseHandle(handle)

    @staticmethod
    def secret(path):
        # ConvertFrom-SecureString without a custom key stores a current-user
        # DPAPI blob encoded as hexadecimal UTF-16 text. Never echo the result.
        import ctypes
        from ctypes import wintypes
        class _Blob(ctypes.Structure):
            _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
        try:
            canonical(path)
            if Path(path).stat().st_size > 32768:
                raise ValueError()
            raw = bytes.fromhex(Path(path).read_text(encoding='utf-8-sig').strip())
            source_buffer = ctypes.create_string_buffer(raw)
            source = _Blob(len(raw), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
            target = _Blob()
            crypt = ctypes.WinDLL('crypt32', use_last_error=True)
            crypt.CryptUnprotectData.restype = ctypes.c_int
            crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
            if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
                raise ValueError()
            try:
                text = ctypes.string_at(target.pbData, target.cbData).decode('utf-16-le').strip()
            finally:
                ctypes.memset(target.pbData, 0, target.cbData)
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.LocalFree.argtypes = [ctypes.c_void_p]
                kernel.LocalFree.restype = ctypes.c_void_p
                kernel.LocalFree(target.pbData)
            if not text.startswith('sk-') or len(text) > 2048:
                raise ValueError()
            return text
        except (ValueError, OSError, UnicodeError):
            raise LifecycleError('CREDENTIAL_UNAVAILABLE') from None

    def tunnel_id(self):
        return json.loads((self.p.directory / 'connection.json').read_text(encoding='utf-8-sig'))['tunnel_id']

    @property
    def task_arguments(self):
        return '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"' + str(self.p.directory/'Run-Work-Connection.ps1') + '\"'

    def task(self, action):
        return self.ps("$identity=[Security.Principal.WindowsIdentity]::GetCurrent(); $task=Get-ScheduledTask -TaskPath '\\' -TaskName $request.name -ErrorAction SilentlyContinue; "
            "if($task){$taskSid=$task.Principal.UserId; if($taskSid -ne $identity.User.Value){try{$taskSid=([Security.Principal.NTAccount]::new($task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value}catch{$taskSid=$null}}; if(@($task.Actions).Count -ne 1 -or $task.Actions[0].Execute -ine $request.exe -or "
            "$task.Actions[0].Arguments -ine $request.arguments -or $task.Actions[0].WorkingDirectory -ine $request.directory -or $taskSid -ne $identity.User.Value){throw 'Task ownership conflict'}; "
            "if($request.action -eq 'stop'){Disable-ScheduledTask -TaskPath '\\' -TaskName $request.name|Out-Null}; "
            "@{exists=$true;state=$task.State.ToString();enabled=[bool]$task.Settings.Enabled}|ConvertTo-Json -Compress}",
            {'name': self.p.task_name, 'action': action, 'exe': self.powershell,
             'arguments': self.task_arguments, 'directory': str(self.p.directory)})


    def enable(self):
        # Explicit entrypoint only; installation/upgrade never calls this.
        return self.ps("$owner=[Security.Principal.WindowsIdentity]::GetCurrent(); $old=Get-ScheduledTask -TaskPath '\\' -TaskName $request.name -ErrorAction SilentlyContinue; "
            "$oldSid=$null; if($old){$oldSid=$old.Principal.UserId; if($oldSid -ne $owner.User.Value){try{$oldSid=([Security.Principal.NTAccount]::new($old.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value}catch{$oldSid=$null}}}; if($old -and (@($old.Actions).Count -ne 1 -or $old.Actions[0].Execute -ine $request.exe -or "
            "$old.Actions[0].Arguments -ine $request.arguments -or $old.Actions[0].WorkingDirectory -ine $request.directory -or $oldSid -ne $owner.User.Value)){throw 'Task ownership conflict'}; "
            "$identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            "$action=New-ScheduledTaskAction -Execute $request.exe -Argument $request.arguments -WorkingDirectory $request.directory; "
            "$trigger=New-ScheduledTaskTrigger -AtLogOn -User $identity; "
            "$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited; "
            "$settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            "-ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1); "
            "Register-ScheduledTask -TaskPath '\\' -TaskName $request.name -Action $action -Trigger $trigger -Principal $principal "
            "-Settings $settings -Description 'Private UoE Work connector' -Force|Out-Null; "
            "Start-ScheduledTask -TaskPath '\\' -TaskName $request.name; @{startup_enabled=$true;readiness='not_checked'}|ConvertTo-Json -Compress",
            {'name': self.p.task_name, 'exe': self.powershell, 'directory': str(self.p.directory),
             'arguments': self.task_arguments})


def stop_supervisor(profile, backend):
    """Disable scheduling separately, then terminate exact transport owners only.

    Do not stop the Task Scheduler job/tree: detached school jobs may belong to
    it. These native handles terminate individual processes, never descendants.
    Killing a wrapper can race a last supervisor spawn, so inspect again before
    entering the connector lock. Unknown/competing identities stop the sequence.
    """
    for _ in range(3):
        rows=backend.processes()
        wrappers=[p for p in rows if profile.wrapper(p)]
        owners=[p for p in rows if profile.supervisor(p)]
        if len(wrappers)>1 or len(owners)>1:
            raise LifecycleError('COMPETING_SUPERVISORS')
        if not wrappers and not owners:
            return
        for owner in wrappers + owners:
            backend.terminate(owner)
    raise LifecycleError('SUPERVISOR_STOP_UNCONFIRMED')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'stop', 'enable'])
    parser.add_argument('--connection-directory', type=Path, required=True)
    parser.add_argument('--connect-once', action='store_true')
    args = parser.parse_args(argv)
    try:
        profile = load_profile(args.connection_directory)
        backend = WindowsBackend(profile)
        if args.action == 'enable':
            output = backend.enable()
            print(json.dumps(output))
            return 0
        if args.action == 'stop':
            backend.task('stop')
            stop_supervisor(profile, backend)
        with ownership_lock(profile, timeout=5 if args.action == 'stop' else 0):
            supervisor = Supervisor(profile, backend)
            output = supervisor.stop() if args.action == 'stop' else supervisor.run(args.connect_once)
        print(json.dumps(output, ensure_ascii=False))
        return 0
    except LifecycleError as error:
        print(json.dumps({'ready': False, 'error_code': error.code, 'scope': 'local_transport_only'}))
        return 1
    except (OSError, ValueError, KeyError):
        print(json.dumps({'ready': False, 'error_code': 'LOCAL_CONFIGURATION_ERROR'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
