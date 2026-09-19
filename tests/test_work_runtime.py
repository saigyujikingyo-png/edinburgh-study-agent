"""Synthetic lifecycle failures; never opens a campus session or a real tunnel."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from edinburgh_study_agent.work_runtime import (
    LifecycleError, Process, Profile, Supervisor, WindowsBackend, ownership_lock,
)


@pytest.fixture
def profile(tmp_path):
    root = tmp_path / 'work'
    root.mkdir()
    return Profile(root, tmp_path, 'synthetic-uoe', str(root/'profiles'),
                   str(root/'client.exe'), str(tmp_path/'runtime/Scripts/python.exe'),
                   tmp_path/'secrets/example.dpapi', 'Synthetic UoE fixture')


def daemon(p, pid=101, born='2026-01-01T00:00:00.0000000+00:00'):
    return Process(pid, 1, p.client, born,
                   (p.client, '--profile', p.alias, '--profile-dir', p.profile_directory))


def child(p, parent, pid=102):
    return Process(pid, parent.pid, p.python, '2026-01-01T00:00:01.0000000+00:00',
                   (p.python, '-m', 'edinburgh_study_agent.server'))


class Fake:
    def __init__(self, p):
        self.p, self.rows, self.calls, self.killed, self.sleeps = p, [], [], [], []
        self.now, self.connect_code, self.stop_code, self.secret_reads = 0., 0, 0, 0
        self.spawn = True
        self.status_values = []
        self.status_error = None
        self.command_delay = 0
        self.query_delay = 0
        self.health = True

    def monotonic(self): return self.now
    def wall_time(self): return str(self.now)
    def self_pid(self): return 900
    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
    def processes(self, timeout=10):
        self.now += min(timeout, self.query_delay)
        if self.query_delay > timeout: raise LifecycleError('COMMAND_TIMEOUT')
        return list(self.rows)
    def process(self, pid, timeout=10): return next((p for p in self.rows if p.pid == pid), None)
    def terminate(self, expected, timeout=10):
        assert self.process(expected.pid) == expected
        self.killed.append(expected.pid)
        self.rows.remove(expected)
    def secret(self, path):
        self.secret_reads += 1
        return 'sk-synthetic-only'
    def tunnel_id(self): return 'tunnel_'+'0'*32
    def status(self):
        owned = [p for p in self.rows if self.p.daemon(p)]
        return dict(process_running=bool(owned), healthy=bool(owned) and self.health,
                    ready=bool(owned) and self.health,
                    process={'pid': owned[0].pid} if owned else None)
    def client(self, args, timeout, *, env=None):
        self.calls.append((args[1], timeout))
        self.now += min(timeout, self.command_delay)
        if self.command_delay > timeout: raise LifecycleError('COMMAND_TIMEOUT')
        if args[1] == 'connect':
            assert env['CONTROL_PLANE_API_KEY'] == 'sk-synthetic-only'
            if self.spawn:
                parent = daemon(self.p)
                self.rows.extend([parent, child(self.p, parent)])
            return dict(code=self.connect_code, stdout='')
        if args[1] == 'stop':
            return dict(code=self.stop_code, stdout='')  # deliberately no cleanup
        if self.status_error: raise LifecycleError(self.status_error)
        result = self.status_values.pop(0) if self.status_values else self.status()
        if isinstance(result, str): return dict(code=0, stdout=result)
        return dict(code=0, stdout=json.dumps(result))


def count(b, action): return sum(a == action for a, _ in b.calls)


def test_delayed_existing_owner_reuses_same_daemon(profile):
    b = Fake(profile); d = daemon(profile); b.rows = [d, child(profile, d)]
    pending = dict(process_running=True, healthy=True, ready=False, process={'pid': d.pid})
    b.status_values = [pending, pending]
    result = Supervisor(profile, b).run(once=True)
    assert result['ready'] and count(b, 'connect') == 0 and b.secret_reads == 0
    assert b.sleeps == [1, 1] and not b.killed
    assert json.loads((profile.directory/'error.json').read_text())['resolved'] is True


@pytest.mark.parametrize('spawn', [False, True])
def test_failed_connect_reconciles_possible_spawn(profile, spawn):
    b = Fake(profile); b.connect_code = 7; b.spawn = spawn
    with pytest.raises(LifecycleError, match='CONNECT_FAILED'):
        Supervisor(profile, b).run(once=True)
    assert sorted(b.killed) == ([101, 102] if spawn else [])
    assert count(b, 'connect') == 1 and not b.rows
    assert json.loads(profile.state_path.read_text())['ready'] is False


def test_registry_stop_failure_still_reconciles_proven_owned_processes(profile):
    b = Fake(profile); b.stop_code = 1; d = daemon(profile)
    other = replace(d, pid=103, argv=(profile.client, '--profile', 'other', '--profile-dir', profile.profile_directory))
    b.rows = [d, child(profile, d), other]
    result = Supervisor(profile, b).stop()
    assert result['state'] == 'stopped' and b.killed == [101, 102] and b.rows == [other]


@pytest.mark.parametrize('error', ['STATUS_FAILED', 'COMMAND_TIMEOUT'])
def test_missing_registry_does_not_prevent_exact_fallback(profile, error):
    b = Fake(profile); b.status_error = error; d = daemon(profile); b.rows = [d, child(profile, d)]
    Supervisor(profile, b).stop()
    assert b.killed == [101, 102] and count(b, 'stop') == 0


def test_foreign_registry_is_preserved(profile):
    b = Fake(profile); foreign = replace(daemon(profile), pid=404, executable=str(profile.home/'foreign.exe'))
    b.rows = [foreign]
    b.status_values = [dict(process_running=True, healthy=True, ready=True, process={'pid':404})]
    with pytest.raises(LifecycleError, match='OWNERSHIP_UNKNOWN'):
        Supervisor(profile, b).stop()
    assert count(b, 'stop') == 0 and not b.killed


def test_total_deadline_includes_slow_status_and_process_query(profile):
    b = Fake(profile); b.rows = [daemon(profile)]; b.health = False
    b.command_delay = 4; b.query_delay = 3
    with pytest.raises(LifecycleError, match='READINESS_TIMEOUT|COMMAND_TIMEOUT'):
        Supervisor(profile, b, readiness_seconds=8).connect()
    assert b.now <= 8 and count(b, 'connect') == 0


def test_live_but_unhealthy_process_is_not_accepted(profile):
    b = Fake(profile); d = daemon(profile); b.rows = [d, child(profile, d)]
    good = b.status()
    b.status_values = [good]
    b.health = False
    with pytest.raises(LifecycleError, match='UNHEALTHY'):
        Supervisor(profile, b, retries=()).run()
    assert count(b, 'connect') == 0 and b.killed == [101, 102]
    assert json.loads(profile.state_path.read_text())['ready'] is False


def test_invalid_status_clears_prior_ready(profile):
    b = Fake(profile); d = daemon(profile); b.rows = [d]
    s = Supervisor(profile, b); s.daemon = d; s.receipt('ready', ready=True)
    b.status_values = ['malformed', 'malformed']
    with pytest.raises(LifecycleError, match='STATUS_INVALID'):
        s.run(once=True)
    assert json.loads(profile.state_path.read_text())['ready'] is False


def test_competing_owners_are_preserved_without_connect_or_stop(profile):
    b = Fake(profile); b.rows = [daemon(profile), daemon(profile, 202)]
    with pytest.raises(LifecycleError, match='COMPETING_OWNERS'):
        Supervisor(profile, b).run(once=True)
    assert not b.killed and count(b, 'stop') == count(b, 'connect') == 0


def test_competing_mcp_children_cannot_be_ready(profile):
    b = Fake(profile); d = daemon(profile); b.rows = [d, child(profile,d), child(profile,d,103)]
    with pytest.raises(LifecycleError, match='COMPETING_CHILDREN'):
        Supervisor(profile, b).run(once=True)
    assert not b.killed


def test_retained_orphan_is_cleaned_but_reused_pid_is_not(profile):
    b = Fake(profile); d = daemon(profile); c = child(profile,d)
    s = Supervisor(profile,b); s.known = {d.pid:d, c.pid:c}; s.receipt('unknown')
    b.rows = [c, replace(d, executable=str(profile.home/'unrelated.exe'))]
    Supervisor(profile,b).stop()
    assert b.killed == [c.pid] and b.rows[0].pid == d.pid


def test_child_birth_before_reused_parent_is_not_owned(profile):
    b = Fake(profile); d = daemon(profile, born='2026-01-02T00:00:00.0000000+00:00')
    c = child(profile,d); b.rows = [d,c]
    Supervisor(profile,b).stop()
    assert b.killed == [d.pid] and b.rows == [c]


def test_bounded_retry_reconciles_before_every_new_connect(profile):
    b = Fake(profile); b.connect_code = 7
    with pytest.raises(LifecycleError, match='CONNECT_FAILED'):
        Supervisor(profile,b,retries=(2,3)).run()
    assert count(b,'connect') == 3 and b.sleeps == [2,3]
    assert b.killed == [101,102] * 3 and b.rows == []


def test_concurrent_owner_lock_is_exclusive_and_released(profile):
    with ownership_lock(profile):
        with pytest.raises(LifecycleError, match='OWNER_BUSY'):
            with ownership_lock(profile): pass
    with ownership_lock(profile): pass


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows subprocess timeout adapter')
def test_external_command_timeout_is_bounded_and_reaps_process(profile):
    b = WindowsBackend(profile); start = time.monotonic()
    with pytest.raises(LifecycleError, match='COMMAND_TIMEOUT'):
        b.command([sys.executable, '-c', 'import time; time.sleep(60)'], .2)
    assert time.monotonic() - start < 5


@pytest.mark.skipif(os.name != 'nt', reason='Current-user Windows DPAPI interoperability')
def test_powershell_dpapi_roundtrip_uses_synthetic_secret(profile):
    b = WindowsBackend(profile)
    value = b.ps("$s=ConvertTo-SecureString ('s'+'k-synthetic-fixture-only') -AsPlainText -Force; try{ConvertFrom-SecureString $s|ConvertTo-Json -Compress}finally{$s.Dispose()}")
    profile.secret_file.parent.mkdir()
    profile.secret_file.write_text(value, encoding='utf-8')
    assert b.secret(profile.secret_file) == 's'+'k-synthetic-fixture-only'


@pytest.mark.skipif(os.name != 'nt', reason='Native Windows owned process handle fence')
def test_native_terminate_preserves_changed_identity_and_reaps_exact_child(profile):
    b = WindowsBackend(profile)
    proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], creationflags=0x08000000)
    try:
        observed = b.process(proc.pid)
        assert observed is not None
        with pytest.raises(LifecycleError, match='OWNER_CHANGED'):
            b.terminate(replace(observed, born='2020-01-01T00:00:00.0000000+00:00'))
        assert proc.poll() is None
        b.terminate(observed)
        assert proc.wait(timeout=3) != 0
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=3)


@pytest.mark.parametrize('boundary', ['registry_stop', 'terminate'])
def test_child_born_during_cleanup_blocks_retry_when_lineage_was_not_observed(profile, boundary):
    b=Fake(profile); d=daemon(profile); b.rows=[d, child(profile,d)]
    normal_client, normal_terminate = b.client, b.terminate
    def late_spawn():
        b.rows.append(child(profile,d,103))
        b.rows.remove(d)
    def client_call(args, timeout, **kw):
        if args[1] == 'stop' and boundary == 'registry_stop': late_spawn()
        return normal_client(args,timeout,**kw)
    def terminate_call(expected, **kwargs):
        if expected == d and boundary == 'terminate': late_spawn()
        else: normal_terminate(expected)
    b.client, b.terminate = client_call, terminate_call
    s=Supervisor(profile,b)
    with pytest.raises(LifecycleError, match='ORPHAN_OWNERSHIP_UNKNOWN'):
        s.stop()
    assert b.process(103) is not None and count(b,'connect') == 0
    with pytest.raises(LifecycleError, match='ORPHAN_OWNERSHIP_UNKNOWN'):
        s.run(once=True)
    assert count(b,'connect') == 0


def test_child_observed_before_parent_exit_is_reconciled(profile):
    b=Fake(profile); d=daemon(profile); b.rows=[d]
    normal=b.client
    def client(args,timeout,**kw):
        if args[1]=='stop': b.rows.append(child(profile,d))
        return normal(args,timeout,**kw)
    b.client=client
    Supervisor(profile,b).stop()
    assert b.killed==[101,102] and not b.rows


def test_two_accounts_and_same_home_host_frontend_are_isolated(profile):
    b=Fake(profile); d=daemon(profile)
    alternate=replace(profile, alias='other-uoe', profile_directory=str(profile.directory/'other'))
    other=daemon(alternate,301); other_child=child(alternate,other,302)
    frontend=replace(child(profile,d,501),parent=500)
    b.rows=[d,child(profile,d),other,other_child,frontend]
    Supervisor(profile,b).stop()
    assert b.rows==[other,other_child,frontend]


def test_linear_venv_redirector_chain_is_one_server_but_branch_is_rejected(profile):
    base=profile.home/'base/python.exe'; base.parent.mkdir(); base.touch()
    cfg=profile.home/'runtime/pyvenv.cfg'; cfg.parent.mkdir()
    cfg.write_text('executable = '+str(base))
    b=Fake(profile); d=daemon(profile); c=child(profile,d)
    inner=replace(child(profile,c,103),executable=str(base))
    b.rows=[d,c,inner]
    assert Supervisor(profile,b).run(once=True)['ready']
    b.rows.append(replace(inner,pid=104))
    with pytest.raises(LifecycleError,match='COMPETING_CHILDREN'):
        Supervisor(profile,b).run(once=True)


def test_replaced_process_is_preserved_during_cleanup(profile):
    b=Fake(profile); d=daemon(profile); b.rows=[d]
    def replaced(pid, **kwargs):
        return replace(d,born='2026-02-01T00:00:00.0000000+00:00')
    b.process=replaced
    with pytest.raises(LifecycleError,match='OWNER_CHANGED'): Supervisor(profile,b).stop()
    assert not b.killed


def test_corrupt_ownership_receipt_cannot_authorize_unrelated_cleanup(profile):
    b=Fake(profile)
    p=replace(daemon(profile), executable=str(profile.home/'unrelated.exe'))
    profile.state_path.write_text(json.dumps(dict(scope=profile.scope,owned=[p.record()])))
    with pytest.raises(LifecycleError,match='INVALID_OWNERSHIP_RECEIPT'): Supervisor(profile,b)


@pytest.mark.parametrize('aliases',[[],[{'alias':'synthetic-uoe'}]])
def test_first_connect_requires_successful_directory_proof_of_absence(profile,aliases):
    b=Fake(profile);normal=b.client
    first=[True]
    def client(args,timeout,**kw):
        if args[1]=='status' and first[0]:
            first[0]=False
            return {'code':1,'stdout':''}
        if args[1]=='list': return {'code':0,'stdout':json.dumps({'aliases':aliases})}
        return normal(args,timeout,**kw)
    b.client=client
    if aliases:
        with pytest.raises(LifecycleError,match='STATUS_FAILED'): Supervisor(profile,b).run(once=True)
        assert count(b,'connect')==0
    else:
        assert Supervisor(profile,b).run(once=True)['ready']
        assert count(b,'connect')==1


def test_explicit_stop_fences_manual_supervisor_and_preserves_other_profiles(profile):
    from edinburgh_study_agent.work_runtime import stop_supervisor
    b=Fake(profile)
    owner=Process(801,1,profile.python,'2026-01-01T00:00:00.0000000+00:00',
      (profile.python,'-m','edinburgh_study_agent.work_runtime','run','--connection-directory',str(profile.directory)))
    other=replace(owner,pid=802,argv=owner.argv[:-1]+(str(profile.directory/'other'),))
    b.rows=[owner,other]
    stop_supervisor(profile,b)
    assert b.killed==[801] and b.rows==[other]


def test_cleanup_commands_share_a_total_budget(profile):
    b=Fake(profile); d=daemon(profile);b.rows=[d,child(profile,d)]
    b.command_delay=10; b.query_delay=10
    with pytest.raises(LifecycleError,match='COMMAND_TIMEOUT|CLEANUP_UNCONFIRMED|READINESS_TIMEOUT'):
        Supervisor(profile,b).stop()
    assert b.now<=45


def test_failed_stop_invalidates_an_earlier_ready_receipt(profile):
    b=Fake(profile);d=daemon(profile);b.rows=[d,child(profile,d)]
    s=Supervisor(profile,b);s.connect()
    def fail(*args,**kwargs):raise LifecycleError('CLEANUP_ACCESS_DENIED')
    b.terminate=fail
    with pytest.raises(LifecycleError,match='CLEANUP_ACCESS_DENIED'):s.stop()
    receipt=json.loads(profile.state_path.read_text())
    assert receipt['state']=='unknown' and receipt['ready'] is False
