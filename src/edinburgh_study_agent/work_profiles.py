"""Release-owned Work launch shims and conservative per-account migration.

Configuration, encrypted secrets and remote app identities are never rewritten.
Installer transactions may roll these owned launcher files back with the runtime.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from . import __version__


NAMES = ('Run-Work-Connection.ps1', 'Stop-Work-Connection.ps1', 'Enable-Work-Connection.ps1')
LEGACY_HASHES = {
    NAMES[0]: {'8e7ecc60b8303ff98a8e672e7a214d5c95ccc36cfb900b8e68a27913a7dfb6ae',
               '22ce7e4fe19a0328407f62dcbb1f1ca6bf4c39ef428378babf8cd774de09bff6'},
    NAMES[1]: {'a2a5df035591b6c188e26c78202960eb8004d7572bbe41aacdb08d57f235ae1e',
               '54cc3841e9b0496b5138d7c9ba09162ec2b6dbd932186fe5ec7719379abe1865'},
    NAMES[2]: {'7769e4568e325a1a89a795ea0de3a4a0c4df1a21300eec0bcf8cb891d42332e9',
               '252bfb670698ccd5dfe64152cac512fd9316cb3d4b993a0d4efa757e67ef60b1'},
}


def normalized_digest(data):
    return hashlib.sha256(data.decode('utf-8-sig').replace('\r\n', '\n').strip().encode()).hexdigest()


def wrapper(action):
    if action not in ('run', 'stop', 'enable'):
        raise ValueError('Unsupported launcher action')
    # Installed copies discover their own account directory. Source entrypoints
    # retain the primary-profile default. No private identity is baked into code.
    text = """# UoE release-owned launch shim. Policy lives in the installed Python package.
param([switch]$ConnectOnce)
$ErrorActionPreference = 'Stop'
$workRoot = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $workRoot 'connection.json') -PathType Leaf)) {
    $workRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.edinburgh-study-agent\\work'
}
if ((Split-Path $workRoot -Leaf) -eq 'work') { $studyRoot = Split-Path $workRoot -Parent }
elseif ((Split-Path (Split-Path $workRoot -Parent) -Leaf) -eq 'accounts') {
    $studyRoot = Split-Path (Split-Path (Split-Path $workRoot -Parent) -Parent) -Parent
} else { throw 'Unsupported UoE connection directory.' }
$python = Join-Path $studyRoot 'runtime\\Scripts\\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'UoE runtime is missing.' }
$arguments = @('-m','edinburgh_study_agent.work_runtime','ACTION','--connection-directory',$workRoot)
if ($ConnectOnce) { $arguments += '--connect-once' }
& $python @arguments
exit $LASTEXITCODE
"""
    return text.replace("'ACTION'", "'"+action+"'").encode('utf-8-sig')


def inspect_profile(directory, *, declaration=None):
    from .work_runtime import canonical, LifecycleError
    directory = Path(canonical(directory))
    if directory.name.casefold() == 'work':
        home = directory.parent
    elif directory.parent.name.casefold() == 'accounts' and directory.parent.parent.name.casefold() == 'work':
        home = directory.parent.parent.parent
    else:
        raise LifecycleError('PROFILE_LOCATION_INVALID')
    config_path = directory/'connection.json'
    canonical(config_path)
    config = json.loads(config_path.read_text(encoding='utf-8-sig'))
    alias = config.get('alias', '')
    if (not re.fullmatch(r'[a-z][a-z0-9-]{2,63}', alias)
            or not re.fullmatch(r'tunnel_[a-f0-9]{16,64}', config.get('tunnel_id', ''))
            or config.get('module', 'edinburgh_study_agent.server') != 'edinburgh_study_agent.server'):
        raise LifecycleError('PROFILE_IDENTITY_INVALID')
    python = Path(canonical(config['python']))
    client = Path(canonical(config['client']))
    profile_directory = Path(canonical(config['profile_directory']))
    if (python != Path(canonical(home/'runtime/Scripts/python.exe')) or not python.is_file()
            or not client.is_file() or client.suffix.casefold() != '.exe'
            or not profile_directory.is_relative_to(directory)):
        raise LifecycleError('PROFILE_PATH_INVALID')
    declaration_path = directory/'lifecycle.json'
    canonical(declaration_path)
    if declaration is None and declaration_path.exists():
        declaration = json.loads(declaration_path.read_text(encoding='utf-8-sig'))
    if declaration is None:
        # Deliberately bounded migration of the two previously shipped shapes.
        if directory == home/'work' and alias == 'edinburgh-study-agent':
            task, secret = 'Edinburgh Study Agent - Work connection', 'secrets/work-tunnel-key.dpapi'
        elif directory.name == 'school-chatgpt' and alias == 'uoe-companion-school':
            task, secret = 'UoE Companion - School account connection', 'secrets/work-school-chatgpt-key.dpapi'
        else:
            raise LifecycleError('PROFILE_DECLARATION_REQUIRED')
        declaration = dict(schema_version=1, alias=alias, task_name=task, secret_file=secret)
    if declaration.get('schema_version') != 1 or declaration.get('alias') != alias:
        raise LifecycleError('PROFILE_DECLARATION_CONFLICT')
    task = declaration.get('task_name')
    if not isinstance(task, str) or not 3 <= len(task) <= 160 or any(ord(c) < 32 or c in '\\/*?[]' for c in task):
        raise LifecycleError('TASK_NAME_INVALID')
    secret = Path(canonical(home/declaration['secret_file']))
    if secret.parent != Path(canonical(home/'secrets')) or secret.suffix != '.dpapi':
        raise LifecycleError('SECRET_REFERENCE_INVALID')
    return dict(directory=directory, home=home, alias=alias, profile_directory=str(profile_directory),
                client=str(client), python=str(python), secret_file=secret, task_name=task,
                declaration=declaration)


@dataclass
class Change:
    path: Path
    before: bytes | None
    after: bytes


def profile_plan(directory, *, declaration=None):
    from .work_runtime import canonical, LifecycleError
    value = inspect_profile(directory, declaration=declaration)
    directory = value['directory']
    declared = value['declaration']
    changes = []
    hashes = {}
    for name, action in zip(NAMES, ('run', 'stop', 'enable')):
        path = directory/name
        canonical(path)
        old = path.read_bytes() if path.exists() else None
        new = wrapper(action)
        if old is not None and old != new:
            expected = declared.get('wrapper_hashes', {}).get(name)
            if hashlib.sha256(old).hexdigest() != expected and normalized_digest(old) not in LEGACY_HASHES[name]:
                raise LifecycleError('CUSTOM_LAUNCHER_PRESERVED')
        hashes[name] = hashlib.sha256(new).hexdigest()
        if old != new:
            changes.append(Change(path, old, new))
    manifest = {**declared, 'schema_version': 1, 'launcher_contract': 1,
                'source_version': __version__, 'wrapper_hashes': hashes}
    path = directory/'lifecycle.json'
    old = path.read_bytes() if path.exists() else None
    new = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()
    if old != new:
        changes.append(Change(path, old, new))
    return changes


def plan(home):
    from .work_runtime import canonical
    home = Path(canonical(home))
    primary = home/'work'
    directories = ([primary] if (primary/'connection.json').exists() else [])
    accounts = primary/'accounts'
    canonical(accounts)
    if accounts.exists():
        directories.extend(sorted(p.parent for p in accounts.glob('*/connection.json')))
    changes, scopes, tasks, aliases = [], set(), set(), set()
    for directory in directories:
        value = inspect_profile(directory)
        scope = (value['alias'].casefold(), value['profile_directory'])
        if scope in scopes or value['task_name'].casefold() in tasks or value['alias'].casefold() in aliases:
            raise ValueError('Conflicting managed account scope')
        scopes.add(scope); tasks.add(value['task_name'].casefold()); aliases.add(value['alias'].casefold())
        changes.extend(profile_plan(directory))
    return changes


def apply(changes):
    from .work_runtime import canonical, LifecycleError
    import os
    import uuid
    written = []
    try:
        for change in changes:
            canonical(change.path)
            current = change.path.read_bytes() if change.path.exists() else None
            if current != change.before:
                raise LifecycleError('LAUNCHER_CHANGED_CONCURRENTLY')
            temporary = change.path.with_name(change.path.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_bytes(change.after)
                os.replace(temporary, change.path)
            finally:
                temporary.unlink(missing_ok=True)
            written.append(change)
        return written
    except Exception:
        rollback(written)
        raise


def rollback(changes):
    from .work_runtime import canonical, LifecycleError
    import os
    import uuid
    conflicts = []
    for change in reversed(changes):
        canonical(change.path)
        if not change.path.exists() or change.path.read_bytes() != change.after:
            conflicts.append(change.path.name)
            continue
        if change.before is None:
            change.path.unlink()
        else:
            temp = change.path.with_name(change.path.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                temp.write_bytes(change.before); os.replace(temp, change.path)
            finally:
                temp.unlink(missing_ok=True)
    if conflicts:
        raise LifecycleError('LAUNCHER_ROLLBACK_CONFLICT')


def activity(profile):
    """Read-only preflight; installation never disables/enables startup tasks."""
    import os
    if os.name != 'nt':
        return {'running': False, 'legacy_startup_enabled': False}
    from .work_runtime import WindowsBackend
    backend=WindowsBackend(profile)
    rows=backend.processes()
    task=backend.task('inspect') or {}
    launcher=profile.directory/NAMES[0]
    legacy=launcher.exists() and launcher.read_bytes() != wrapper('run')
    return dict(running=any(profile.daemon(p) or profile.supervisor(p) for p in rows),
                legacy_startup_enabled=legacy and task.get('enabled') is True)


@contextmanager
def upgrade_guard(home):
    """Share launch locks while upgrading. Old unmanaged launchers must be paused."""
    from .work_runtime import load_profile, ownership_lock, canonical
    home=Path(canonical(home))
    primary=home/'work'
    directories=([primary] if (primary/'connection.json').exists() else [])
    accounts=primary/'accounts';canonical(accounts)
    if accounts.exists():
        directories.extend(sorted(p.parent for p in accounts.glob('*/connection.json')))
    with ExitStack() as locks:
        for directory in directories:
            profile=load_profile(directory)
            locks.enter_context(ownership_lock(profile))
            observed=activity(profile)
            if observed['running'] or observed['legacy_startup_enabled']:
                raise ValueError('Pause this Work connection with its Stop entrypoint before upgrading; startup and accounts were preserved.')
        yield


def save_backup(home, changes):
    """Retain a read-back-verified launcher backup alongside runtime rollback."""
    from datetime import datetime, timezone
    import uuid
    from .work_runtime import atomic_json, canonical
    home = Path(canonical(home))
    backup = home/('lifecycle-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    backup.mkdir()
    rows = []
    for index, change in enumerate(changes):
        path = Path(canonical(change.path))
        if path.name.casefold() not in {n.casefold() for n in (*NAMES, 'lifecycle.json')} or not path.is_relative_to(home/'work'):
            raise ValueError('Unexpected launcher backup path')
        original = None
        if change.before is not None:
            original = f'{index}.before'
            (backup/original).write_bytes(change.before)
            if (backup/original).read_bytes() != change.before:
                raise ValueError('Launcher backup readback failed')
        rows.append(dict(path=path.relative_to(home).as_posix(), before_file=original,
                         before_sha256=hashlib.sha256(change.before).hexdigest() if original else None,
                         after_sha256=hashlib.sha256(change.after).hexdigest()))
    atomic_json(backup/'manifest.json', dict(schema_version=1,source_version=__version__,files=rows))
    return backup


def restore_backup(home, backup):
    """Restore only unchanged owned launcher files; no task or identity changes."""
    from .work_runtime import canonical
    home, backup = Path(canonical(home)), Path(canonical(backup))
    if backup.parent != home or not backup.name.startswith('lifecycle-backup-'):
        raise ValueError('Unexpected launcher backup directory')
    document = json.loads((backup/'manifest.json').read_text(encoding='utf-8'))
    if document.get('schema_version') != 1 or not 0 < len(document.get('files', [])) <= 128:
        raise ValueError('Invalid launcher backup manifest')
    changes=[]
    for row in document['files']:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid backup path')
        path = Path(canonical(home/relative))
        if path.name.casefold() not in {n.casefold() for n in (*NAMES,'lifecycle.json')} or not path.is_relative_to(home/'work'):
            raise ValueError('Invalid backup path')
        after=path.read_bytes()
        if hashlib.sha256(after).hexdigest() != row['after_sha256']:
            raise ValueError('Launcher changed since this backup; it was preserved')
        before=None
        if row['before_file'] is not None:
            source=Path(canonical(backup/row['before_file']))
            if source.parent != backup:
                raise ValueError('Invalid backup file')
            before=source.read_bytes()
            if hashlib.sha256(before).hexdigest() != row['before_sha256']:
                raise ValueError('Launcher backup checksum mismatch')
        changes.append(Change(path,before,after))
    rollback(changes)
    return len(changes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare'])
    parser.add_argument('--connection-directory', type=Path, required=True)
    parser.add_argument('--alias', required=True)
    parser.add_argument('--task-name', required=True)
    parser.add_argument('--secret-file', required=True, help='Relative to the private UoE home; no secret value')
    args = parser.parse_args(argv)
    declaration = dict(schema_version=1, alias=args.alias, task_name=args.task_name, secret_file=args.secret_file)
    existing = args.connection_directory/'lifecycle.json'
    if existing.exists():
        prior = json.loads(existing.read_text(encoding='utf-8-sig'))
        if any(prior.get(k) != v for k, v in declaration.items()):
            parser.error('An existing profile declaration differs; it was preserved.')
        declaration = prior
    changes = profile_plan(args.connection_directory, declaration=declaration)
    if changes:
        from .work_runtime import Profile, ownership_lock
        value = inspect_profile(args.connection_directory, declaration=declaration)
        profile = Profile(**{key: value[key] for key in Profile.__dataclass_fields__})
        with ownership_lock(profile):
            observed = activity(profile)
            if observed['running'] or observed['legacy_startup_enabled']:
                parser.error('Pause this account connection before updating its launchers; existing files were preserved.')
            save_backup(profile.home, changes)
            apply(changes)
    print(json.dumps({'changed_files': len(changes), 'startup_changed': False,
                      'account_identity_changed': False, 'secrets_changed': False}))


if __name__ == '__main__':
    main()
