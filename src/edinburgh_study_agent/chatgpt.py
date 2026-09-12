"""Bind a private installed plugin to its owner's ChatGPT Chat/Work connection.

This configures dependency discovery, not cloud installation or authentication.
The public package deliberately never contains a personal app identifier.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .hosts import atomic_json

PLUGIN_NAME = "edinburgh-study-agent"
APP_KEY = "uoe-companion"
GUIDE = "https://github.com/saigyujikingyo-png/edinburgh-study-agent/blob/main/docs/WORK_SETUP.md"


def app_identity(value):
    if not isinstance(value, str):
        raise ValueError("Use your own registered ChatGPT app ID.")
    value = value.removeprefix("plugin_")
    if not re.fullmatch(r"asdk_app_[a-f0-9]{32}", value):
        raise ValueError("Use the actual private app ID from ChatGPT connection settings.")
    return value


def load_object(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("An existing connection file is invalid JSON; it was not replaced.") from exc
    if not isinstance(value, dict):
        raise ValueError("Connection files must contain JSON objects.")
    return value


def binding_path(home):
    return Path(home).resolve() / "work/chatgpt.json"


def plugin_files(plugin):
    plugin = Path(plugin).absolute()
    if plugin.resolve() != plugin or any((parent / ".git").exists() for parent in [plugin, *plugin.parents]):
        raise ValueError("Bind a separate private installed plugin copy, never a Git checkout or symlink.")
    manifest = plugin / ".codex-plugin/plugin.json"
    app = plugin / ".app.json"
    if any(path.resolve() != path for path in (manifest, app)):
        raise ValueError("Plugin connection files must not be symlinks.")
    document = load_object(manifest)
    if document.get("name") != PLUGIN_NAME or plugin.name != PLUGIN_NAME:
        raise ValueError("The destination is not an installed UoE Companion plugin.")
    if document.get("apps") not in (None, "./.app.json"):
        raise ValueError("An existing custom app manifest is present; it was not replaced.")
    return plugin, manifest, app, document


def inspect_binding(home, plugin=None, *, use_saved_plugin=True):
    path = binding_path(home)
    saved = load_object(path) if path.exists() else {}
    identity = app_identity(saved["app_id"]) if saved.get("app_id") else None
    target = plugin or (saved.get("plugin_path") if use_saved_plugin else None)
    configured = False
    if target is not None:
        _, _, app, manifest = plugin_files(target)
        applications = load_object(app).get("apps", {}) if app.exists() else {}
        managed = applications.get(APP_KEY) if isinstance(applications, dict) else None
        configured = (identity is not None and manifest.get("apps") == "./.app.json"
                      and isinstance(managed, dict) and managed.get("id") == identity)
    return {"binding_configured": configured,
            "configuration_scope": "this_person_only",
            "cloud_installation": "not_checked", "cloud_connection": "not_checked",
            "chat_model_roundtrip": "not_checked", "work_model_roundtrip": "not_checked",
            "campus_login": "not_checked", "acceptance": "configuration_only",
            "connection_url": "https://chatgpt.com/plugins/plugin_" + identity if identity else None,
            "setup_guide": GUIDE,
            "next_step": "Install AND connect this personal app in ChatGPT, then test Chat and cloud Work separately. A local stdio check does not prove either surface works."}


def bind(home, plugin, app_id=None):
    home = Path(home).resolve()
    plugin, manifest_path, app_path, manifest = plugin_files(plugin)
    if home == plugin or home.is_relative_to(plugin):
        raise ValueError("Private connection settings must be outside the plugin package.")
    settings_path = binding_path(home)
    if settings_path.resolve() != settings_path:
        raise ValueError("Private connection settings must not be a symlink.")
    previous = load_object(settings_path) if settings_path.exists() else {}
    identity = app_identity(app_id or previous.get("app_id"))
    if previous.get("app_id") and app_identity(previous["app_id"]) != identity:
        raise ValueError("A different personal ChatGPT connection is already bound; it was not replaced.")
    apps = load_object(app_path) if app_path.exists() else {"apps": {}}
    if set(apps) - {"apps"} or not isinstance(apps.get("apps"), dict):
        raise ValueError("The existing app manifest is invalid; it was not replaced.")
    current = apps["apps"].get(APP_KEY)
    if current is not None and (not isinstance(current, dict) or current.get("id") != identity):
        raise ValueError("The plugin already declares a different UoE connection; it was not replaced.")
    apps["apps"][APP_KEY] = {**(current or {}), "id": identity}
    manifest["apps"] = "./.app.json"
    saved = {**previous, "schema_version": 1, "app_id": identity, "plugin_path": str(plugin)}
    documents = [(app_path, apps), (manifest_path, manifest), (settings_path, saved)]
    pending = []
    for path, document in documents:
        before = path.read_bytes() if path.exists() else None
        if before is None or json.loads(before.decode("utf-8-sig")) != document:
            pending.append((path, before, document))
    backup = None
    if pending:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = home / "work/binding-backups" / stamp
        backup.mkdir(parents=True)
        for index, (path, before, _) in enumerate(pending):
            if before is not None:
                (backup / f"{index}-{path.name}").write_bytes(before)
        completed = []
        try:
            for path, before, document in pending:
                if (path.read_bytes() if path.exists() else None) != before:
                    raise ValueError("Plugin configuration changed concurrently; retry the binding.")
                atomic_json(path, document)
                completed.append((path, before))
        except Exception:
            for path, before in reversed(completed):
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(before)
            raise
    return {**inspect_binding(home, plugin), "changed": bool(pending),
            "backup": str(backup) if backup else None,
            "source_package_changed": False,
            "next_step": "Reinstall this private marketplace plugin to load its app dependency. Install AND connect the linked app in ChatGPT. Verify actual Chat and Work calls; this command cannot authenticate the cloud host."}


def configure_installation(home, plugin=None, app_id=None):
    """Reapply an explicit/saved identity, or return a full unconfigured status."""
    if app_id and plugin is None:
        raise ValueError("Supply a separate private plugin copy to bind ChatGPT.")
    path = binding_path(home)
    saved = load_object(path) if path.exists() else {}
    if plugin is not None and (app_id or saved.get("app_id")):
        return bind(home, plugin, app_id)
    # An empty/unrelated settings object is unconfigured, not an invalid identity.
    # Without an explicit plugin target do not follow a potentially stale path.
    return inspect_binding(home, plugin, use_saved_plugin=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["bind", "check", "configure"])
    parser.add_argument("--home", type=Path, default=Path(os.environ.get("EDINBURGH_STUDY_HOME", Path.home() / ".edinburgh-study-agent")))
    parser.add_argument("--plugin-path", type=Path)
    parser.add_argument("--app-id", help="Your own registered private ChatGPT app ID; never a secret.")
    args = parser.parse_args()
    try:
        if args.action == "bind":
            if args.plugin_path is None:
                raise ValueError("Supply the separate private installed --plugin-path.")
            result = bind(args.home, args.plugin_path, args.app_id)
        elif args.action == "configure":
            result = configure_installation(args.home, args.plugin_path, args.app_id)
        else:
            result = inspect_binding(args.home, args.plugin_path)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
