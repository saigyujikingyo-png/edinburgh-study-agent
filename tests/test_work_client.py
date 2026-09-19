"""Opt-in official-client parser/stdio test; loopback only, no account or key.

Set UOE_TEST_TUNNEL_CLIENT to a reviewed local tunnel-client executable.
The default suite skips this test; it never downloads or installs that client.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
import venv

import pytest

from test_work_runtime import Fake, profile
from edinburgh_study_agent.work_runtime import Supervisor

CLIENT = os.environ.get('UOE_TEST_TUNNEL_CLIENT')
pytestmark = pytest.mark.skipif(os.name != 'nt' or not CLIENT,
    reason='Opt-in Windows official tunnel-client loopback fixture')

STUB = r"""
import json, os, pathlib, sys, threading
# A failed parent cannot leave this synthetic fixture resident indefinitely.
watchdog = threading.Timer(12, lambda: os._exit(0)); watchdog.daemon = True; watchdog.start()
receipt = pathlib.Path(os.environ['UOE_FIXTURE_RECEIPT'])
receipt.write_text(json.dumps({'pid':os.getpid(),'executable':sys.executable,'argv':sys.argv}))
for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message:
        continue
    method = message.get('method')
    if method == 'initialize':
        result = {'protocolVersion':message['params']['protocolVersion'],
                  'capabilities':{'tools':{}},
                  'serverInfo':{'name':'UoE synthetic parser fixture','version':'1'}}
        receipt.with_suffix('.initialized').write_text('initialized')
    elif method == 'tools/list':
        result = {'tools':[]}
    else:
        result = {}
    print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result}),flush=True)
"""


def isolated_env(root, receipt, modules):
    env = {key:os.environ[key] for key in
           ('SystemRoot','SYSTEMROOT','WINDIR','SystemDrive','COMSPEC') if key in os.environ}
    env.update({key:str(root/key.lower()) for key in
                ('HOME','USERPROFILE','LOCALAPPDATA','APPDATA','XDG_CONFIG_HOME','XDG_STATE_HOME','TEMP','TMP')})
    for key in ('HOME','USERPROFILE','LOCALAPPDATA','APPDATA','XDG_CONFIG_HOME','XDG_STATE_HOME','TEMP','TMP'):
        Path(env[key]).mkdir(parents=True,exist_ok=True)
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1',
               PYTHONPATH=str(modules), UOE_FIXTURE_RECEIPT=str(receipt),
               EDINBURGH_STUDY_HOME=str(root/'empty-study-home'))
    return env


@pytest.mark.parametrize('directory', ['plain', 'Student Name', "学生 O'Brien & lab (x),$v;g=one"])
def test_official_client_executes_exact_python_and_module(profile, tmp_path, directory):
    runtime = tmp_path/directory
    # Venv's convenience builder refuses semicolons in the destination, although
    # Windows executable paths permit them. Copy its two launch inputs only.
    base = tmp_path/'venv-base'
    venv.EnvBuilder(with_pip=False, symlinks=False).create(base)
    (runtime/'Scripts').mkdir(parents=True)
    shutil.copy2(base/'Scripts/python.exe', runtime/'Scripts/python.exe')
    shutil.copy2(base/'pyvenv.cfg', runtime/'pyvenv.cfg')
    python = runtime/'Scripts/python.exe'
    modules = tmp_path/'modules'
    package = modules/'edinburgh_study_agent'; package.mkdir(parents=True)
    (package/'__init__.py').write_text('')
    (package/'server.py').write_text(STUB,encoding='utf-8')
    p = replace(profile, python=str(python))

    class Capture(Fake):
        def client(self, args, timeout, *, env=None):
            if args[1] == 'connect':
                self.command = args[args.index('--mcp-command')+1]
            return super().client(args, timeout, env=env)

    b = Capture(p)
    assert Supervisor(p,b).run(once=True)['ready']
    for label, command in [('old',subprocess.list2cmdline([str(python),'-m','edinburgh_study_agent.server'])),
                            ('fixed',b.command)]:
        case = tmp_path/label; case.mkdir()
        receipt = case/'stub.json'
        env = isolated_env(case,receipt,modules)
        args = [CLIENT,'dev','proxy','--backend','go','--listen','127.0.0.1:0',
                '--engine-queue-backend','inmem','--profile-dir',str(case/'profiles'),
                '--duration','2s','--readiness-timeout','3s','--print-json',
                '--mcp-command',command]
        started = time.monotonic()
        result = subprocess.run(args,cwd=case,env=env,capture_output=True,text=True,
                                encoding='utf-8',timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        diagnostic = result.stdout + result.stderr
        if label == 'old':
            assert result.returncode != 0 and not receipt.exists(), diagnostic[-2500:]
            assert 'fork/exec' in diagnostic or 'unterminated' in diagnostic, diagnostic[-2500:]
        else:
            assert receipt.exists(), diagnostic[-2500:]
            assert result.returncode == 0, diagnostic[-2500:]
            observed = json.loads(receipt.read_text())
            assert Path(observed['executable']).resolve() == python.resolve()
            assert Path(observed['argv'][0]).resolve() == (package/'server.py').resolve()
        assert time.monotonic() - started < 15
