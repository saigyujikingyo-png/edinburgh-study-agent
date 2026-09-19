"""Multi-account launcher upgrades use synthetic identities and isolated files."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from edinburgh_study_agent import __version__, setup_core, work_profiles as profiles
from edinburgh_study_agent.work_runtime import LifecycleError


@pytest.fixture(autouse=True)
def synthetic_activity(monkeypatch):
    monkeypatch.setattr(profiles, 'activity', lambda p: {'running':False,'legacy_startup_enabled':False})


def configured(home, account=None, declared=False):
    root = home/'work'
    if account: root = root/'accounts'/account
    root.mkdir(parents=True)
    python = home/'runtime/Scripts/python.exe'
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b'prior-runtime')
    client = root/'client.exe'; client.write_bytes(b'synthetic-not-executable')
    alias = 'uoe-companion-school' if account else 'edinburgh-study-agent'
    config = dict(alias=alias,tunnel_id='tunnel_'+'0'*32,client=str(client),python=str(python),
                  profile_directory=str(root/'profiles'),module='edinburgh_study_agent.server')
    (root/'connection.json').write_text(json.dumps(config))
    (root/'chatgpt.json').write_text('{"identity":"synthetic-preserve"}')
    (home/'secrets').mkdir(exist_ok=True)
    (home/'secrets/keep.dpapi').write_bytes(b'synthetic-protected-value')
    if declared:
        declaration=dict(schema_version=1,alias=alias,task_name='Synthetic task '+(account or 'primary'),
                         secret_file='secrets/keep.dpapi')
        (root/'lifecycle.json').write_text(json.dumps(declaration))
    return root


def package(path):
    runtime=path/'runtime/Scripts/python.exe';runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b'updated-runtime')
    (path/'manifest.json').write_text(json.dumps(dict(product='uoe-companion',version=__version__,
         files={'runtime/Scripts/python.exe':setup_core.digest(runtime)})))
    return path


def doctor(*args): return {'version':__version__}


def test_both_profiles_generate_same_launchers_without_identity_secret_or_task_changes(tmp_path):
    home=tmp_path/'home'; primary=configured(home);school=configured(home,'school-chatgpt')
    protected={p:p.read_bytes() for p in (primary/'connection.json',school/'connection.json',
               primary/'chatgpt.json',school/'chatgpt.json',home/'secrets/keep.dpapi')}
    changes=profiles.plan(home);backup=profiles.save_backup(home,changes)
    profiles.apply(changes)
    for name in profiles.NAMES: assert (primary/name).read_bytes()==(school/name).read_bytes()
    assert json.loads((school/'lifecycle.json').read_text())['secret_file']=='secrets/work-school-chatgpt-key.dpapi'
    assert profiles.plan(home)==[]
    assert all(p.read_bytes()==before for p,before in protected.items())
    assert profiles.restore_backup(home,backup)==8
    assert not (school/'lifecycle.json').exists()


def test_custom_launcher_in_any_profile_blocks_all_changes(tmp_path):
    home=tmp_path/'home';primary=configured(home);school=configured(home,'school-chatgpt')
    custom=school/profiles.NAMES[0];custom.write_bytes(b'# intentional user customization')
    with pytest.raises(LifecycleError,match='CUSTOM_LAUNCHER_PRESERVED'): profiles.plan(home)
    assert not (primary/profiles.NAMES[0]).exists() and custom.read_bytes().endswith(b'customization')


def test_unknown_account_needs_explicit_data_declaration(tmp_path):
    root=configured(tmp_path/'home','another-account')
    with pytest.raises(LifecycleError,match='PROFILE_DECLARATION_REQUIRED'): profiles.profile_plan(root)


def test_apply_rolls_back_on_concurrent_edit_without_overwriting_the_edit(tmp_path):
    root=configured(tmp_path/'home');changes=profiles.profile_plan(root)
    changes[1].path.write_bytes(b'user changed meanwhile')
    with pytest.raises(LifecycleError,match='LAUNCHER_CHANGED_CONCURRENTLY'): profiles.apply(changes)
    assert not changes[0].path.exists() and changes[1].path.read_bytes()==b'user changed meanwhile'


def test_persistent_backup_checks_hashes_and_preserves_later_user_changes(tmp_path):
    home=tmp_path/'home';root=configured(home);changes=profiles.plan(home)
    backup=profiles.save_backup(home,changes);profiles.apply(changes)
    changed=root/profiles.NAMES[-1];changed.write_bytes(b'user later edit')
    with pytest.raises(ValueError,match='changed since'): profiles.restore_backup(home,backup)
    assert all(c.path.exists() for c in changes) and changed.read_bytes()==b'user later edit'


def test_release_source_shims_match_generator():
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    for name,action in zip(profiles.NAMES,('run','stop','enable')):
        assert profiles.normalized_digest((scripts/name).read_bytes())==profiles.normalized_digest(profiles.wrapper(action))


def test_upgrade_migrates_both_profiles_and_retains_persistent_rollback(tmp_path,monkeypatch):
    home=tmp_path/'home';root=configured(home);school=configured(home,'school-chatgpt')
    payload=package(tmp_path/'payload')
    monkeypatch.setattr(setup_core,'runtime_processes',lambda runtime:[])
    result=setup_core.install(payload,home,doctor=doctor)
    assert result['launcher_files_updated']==8 and not result['startup_preferences_changed']
    assert Path(result['runtime_backup']).joinpath('Scripts/python.exe').read_bytes()==b'prior-runtime'
    assert Path(result['launcher_backup']).joinpath('manifest.json').is_file()
    assert (school/profiles.NAMES[0]).exists()
    again=setup_core.install(payload,home,doctor=doctor)
    assert again['unchanged_runtime'] and again['launcher_files_updated']==0


def test_late_install_failure_restores_runtime_and_both_account_launchers(tmp_path,monkeypatch):
    home=tmp_path/'home';root=configured(home);school=configured(home,'school-chatgpt')
    payload=package(tmp_path/'payload');host=tmp_path/'host.json'
    host.write_text('{"mcpServers":{"uoe-companion":{"command":"unrelated"}}}')
    monkeypatch.setattr(setup_core,'runtime_processes',lambda runtime:[])
    with pytest.raises(ValueError,match='unrelated'):
        setup_core.install(payload,home,['workbuddy'],config_paths={'workbuddy':host},doctor=doctor)
    assert (home/'runtime/Scripts/python.exe').read_bytes()==b'prior-runtime'
    assert not (root/profiles.NAMES[0]).exists() and not (school/'lifecycle.json').exists()
    assert len(list(home.glob('lifecycle-backup-*/manifest.json')))==1


def test_same_bundle_still_refuses_launcher_migration_while_runtime_busy(tmp_path,monkeypatch):
    home=tmp_path/'home';root=configured(home);payload=package(tmp_path/'payload')
    (home/'runtime/Scripts/python.exe').write_bytes((payload/'runtime/Scripts/python.exe').read_bytes())
    (home/'installation.json').write_text(json.dumps({'bundle_sha256':setup_core.digest(payload/'manifest.json')}))
    monkeypatch.setattr(setup_core,'runtime_processes',lambda runtime:[999])
    with pytest.raises(ValueError,match='in use'): setup_core.install(payload,home,doctor=doctor)
    assert not (root/'lifecycle.json').exists()


@pytest.mark.skipif(os.name!='nt',reason='Windows directory junction boundary')
def test_junction_account_path_is_not_followed(tmp_path):
    import subprocess
    home=tmp_path/'home';root=configured(home)
    other=tmp_path/'external';other.mkdir()
    junction=root/'accounts';junction.mkdir()
    link=junction/'school-chatgpt'
    # mklink is used only to create this isolated test junction; removal uses
    # rmdir on the verified link itself, never a recursive/cross-shell command.
    subprocess.run(['cmd','/c','mklink','/J',str(link),str(other)],check=True,capture_output=True)
    try:
        (other/'connection.json').write_text('{}')
        with pytest.raises(LifecycleError,match='REPARSE_POINT'): profiles.plan(home)
        assert not (root/profiles.NAMES[0]).exists()
    finally: link.rmdir()


@pytest.mark.parametrize('reason',['running','legacy_startup_enabled'])
def test_upgrade_preserves_running_or_enabled_legacy_connection(tmp_path,monkeypatch,reason):
    home=tmp_path/'home';root=configured(home)
    monkeypatch.setattr(profiles,'activity',lambda p:{'running':reason=='running','legacy_startup_enabled':reason=='legacy_startup_enabled'})
    with pytest.raises(ValueError,match='Pause'):
        setup_core.install(package(tmp_path/'payload'),home,doctor=doctor)
    assert (home/'runtime/Scripts/python.exe').read_bytes()==b'prior-runtime'
    assert not (root/'lifecycle.json').exists()


def test_upgrade_holds_same_profile_lock_as_a_new_launcher(tmp_path):
    from edinburgh_study_agent.work_runtime import load_profile,ownership_lock
    home=tmp_path/'home';root=configured(home)
    with profiles.upgrade_guard(home):
        with pytest.raises(LifecycleError,match='OWNER_BUSY'):
            with ownership_lock(load_profile(root)): pass


@pytest.mark.parametrize('name',['all * tasks','[abc] task','task?','task\nnext'])
def test_profile_task_name_cannot_expand_to_other_scheduler_entries(tmp_path,name):
    home=tmp_path/'home';root=configured(home,declared=True)
    declaration=json.loads((root/'lifecycle.json').read_text())
    declaration['task_name']=name
    with pytest.raises(LifecycleError,match='TASK_NAME_INVALID'):
        profiles.inspect_profile(root,declaration=declaration)


def test_explicit_prepare_cannot_replace_a_running_account_launcher(tmp_path,monkeypatch):
    home=tmp_path/'home';root=configured(home)
    monkeypatch.setattr(profiles,'activity',lambda p:{'running':True,'legacy_startup_enabled':False})
    with pytest.raises(SystemExit):
        profiles.main(['prepare','--connection-directory',str(root),'--alias','edinburgh-study-agent',
           '--task-name','Synthetic task','--secret-file','secrets/keep.dpapi'])
    assert not (root/profiles.NAMES[0]).exists()


def test_cli_alias_cannot_be_shared_by_two_different_profile_directories(tmp_path):
    home=tmp_path/'home';primary=configured(home,declared=True)
    other=configured(home,'other-account',declared=True)
    config=json.loads((other/'connection.json').read_text())
    declaration=json.loads((other/'lifecycle.json').read_text())
    config['alias']=declaration['alias']='edinburgh-study-agent'
    (other/'connection.json').write_text(json.dumps(config))
    (other/'lifecycle.json').write_text(json.dumps(declaration))
    with pytest.raises(ValueError,match='Conflicting managed account scope'):profiles.plan(home)
    assert not (primary/profiles.NAMES[0]).exists()
