"""Thin Windows launchers and task adapter; isolated process/task boundaries only.

The legacy policy tests are now exercised against the shared Python supervisor in
test_work_runtime.py, including the previously failing registry-stop regression.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from edinburgh_study_agent import work_profiles
from edinburgh_study_agent.work_runtime import Profile, WindowsBackend

pytestmark=pytest.mark.skipif(os.name!='nt',reason='Windows launcher/task adapter')


@pytest.mark.parametrize('account',[None,'school-chatgpt'])
@pytest.mark.parametrize('action',['run','stop','enable'])
def test_shim_passes_exact_account_and_exit_status_without_another_backend(tmp_path,account,action):
    home=tmp_path/'synthetic 学生 home';root=home/'work'
    if account: root=root/'accounts'/account
    root.mkdir(parents=True);(root/'connection.json').write_text('{}')
    adapter=home/'runtime/Scripts/fixture.ps1';adapter.parent.mkdir(parents=True)
    adapter.write_text("ConvertTo-Json -InputObject @($args) -Compress; exit 7",encoding='utf-8-sig')
    # Substitute only the interpreter path at the process boundary, not policy.
    source=work_profiles.wrapper(action).decode('utf-8-sig')
    assert source.count('runtime\\Scripts\\python.exe')==1
    source=source.replace('runtime\\Scripts\\python.exe','runtime\\Scripts\\fixture.ps1')
    script=root/(action+'.ps1');script.write_text(source,encoding='utf-8-sig')
    shell=shutil.which('pwsh') or shutil.which('powershell')
    result=subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(script),'-ConnectOnce'],
                          capture_output=True,text=True,encoding='utf-8',timeout=10)
    assert result.returncode==7,result.stderr
    assert json.loads(result.stdout)==['-m','edinburgh_study_agent.work_runtime',action,
                                      '--connection-directory',str(root),'--connect-once']


@pytest.mark.parametrize('foreign',['executable','arguments','directory','principal','short_principal','none'])
def test_stop_task_adapter_checks_full_action_before_disabling(tmp_path,foreign):
    p=Profile(tmp_path,tmp_path,'fixture',str(tmp_path/'profiles'),'unused.exe','unused-python.exe',
              tmp_path/'secret.dpapi','Synthetic task')
    backend=WindowsBackend(p)
    row=dict(Execute=backend.powershell,Arguments=backend.task_arguments,WorkingDirectory=str(tmp_path))
    if foreign=='executable':row['Execute']='foreign.exe'
    if foreign=='arguments':row['Arguments'] += ' -Command Unexpected'
    if foreign=='directory':row['WorkingDirectory']=str(tmp_path/'different')
    native_ps=backend.ps
    def fixture_ps(script,payload=None,timeout=10):
        pre="""
$global:trace=@()
function Get-ScheduledTask { param($TaskName,$TaskPath,$ErrorAction) [pscustomobject]@{Actions=@($request.fixture);State='Ready';Principal=@{UserId=$(if($request.foreignPrincipal){'unrelated-account'}elseif($request.shortPrincipal){[Environment]::UserName}else{[Security.Principal.WindowsIdentity]::GetCurrent().Name})}} }
function Disable-ScheduledTask {param($TaskName,$TaskPath) $global:trace+='disable'}
function Stop-ScheduledTask {param($TaskName,$TaskPath) $global:trace+='stop'}
"""
        wrapped=pre+"try { $result=(& { "+script+" })|ConvertFrom-Json; $result|Add-Member trace $global:trace; $result|ConvertTo-Json -Depth 4 -Compress } catch { @{failed=$true;trace=$global:trace}|ConvertTo-Json -Compress }"
        return native_ps(wrapped,{**payload,'fixture':row,'foreignPrincipal':foreign=='principal','shortPrincipal':foreign=='short_principal'},timeout)
    backend.ps=fixture_ps
    result=backend.task('stop')
    if foreign in ('none','short_principal'):assert result['exists'] is True and result['trace']==['disable']
    else:assert result['failed'] is True and result['trace']==[]
