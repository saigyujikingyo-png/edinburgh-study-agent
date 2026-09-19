"""Opt-in, disposable current-user Task Scheduler lifetime acceptance.

Only synthetic modules/processes are launched. No installed account, connector,
credential, campus content or existing scheduled task is used or changed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

from edinburgh_study_agent import __version__, work_runtime
from edinburgh_study_agent.work_runtime import Profile, WindowsBackend, stop_supervisor


def observe_fixture(profile, rows, pids, observed):
    """Append only positively identified fixture processes, even on failure."""
    wrappers = [item for item in rows if profile.wrapper(item)]
    if len(wrappers) != 1:
        raise ValueError('Synthetic wrapper identity was not unique')
    wrapper = wrappers[0]
    observed.append(wrapper)
    owner = next((item for item in rows if item.pid == pids['supervisor']), None)
    if (owner is None or not profile.supervisor(owner)
            or owner.parent != wrapper.pid or owner.born < wrapper.born):
        raise ValueError('Synthetic supervisor identity was not verified')
    observed.append(owner)
    job = next((item for item in rows if item.pid == pids['job']), None)
    if (job is None or job.parent != owner.pid or job.born < owner.born
            or not profile.same_path(job.executable, profile.python)
            or job.argv[1:] != ('-m', 'edinburgh_study_agent.school')):
        raise ValueError('Synthetic job identity was not verified')
    observed.append(job)
    return wrapper, owner, job


def run(receipt):
    if os.name != 'nt':
        raise ValueError('Windows is required')
    name='UoE Lifecycle Acceptance '+uuid.uuid4().hex
    report=dict(schema_version=1,version=__version__,checked_at=datetime.now(timezone.utc).isoformat(),
                scope='synthetic_current_user_scheduler_task', existing_tasks_changed=False,
                real_school_jobs_used=False,registered=False,passed=False,task_name=name,
                runtime_module_sha256=hashlib.sha256(Path(work_runtime.__file__).read_bytes()).hexdigest())
    registered=False
    observed=[]
    root=Path(tempfile.mkdtemp(prefix='uoe-scheduler-acceptance-'))
    report['fixture_directory']=str(root)
    work=root/'work';work.mkdir()
    package=root/'edinburgh_study_agent';package.mkdir()
    (package/'__init__.py').write_text('')
    (package/'work_runtime.py').write_text(
        "import json,os,pathlib,subprocess,sys,time\n"
        "root=pathlib.Path(sys.argv[sys.argv.index('--connection-directory')+1])\n"
        "job=subprocess.Popen([sys.executable,'-m','edinburgh_study_agent.school'],creationflags=subprocess.DETACHED_PROCESS|subprocess.CREATE_NO_WINDOW)\n"
        "(root/'pids.tmp').write_text(json.dumps({'supervisor':os.getpid(),'job':job.pid}))\n"
        "(root/'pids.tmp').replace(root/'pids.json')\n"
        "time.sleep(90)\n")
    (package/'school.py').write_text(
        "import pathlib,time\n"
        "file=pathlib.Path(__file__).parent.parent/'job-heartbeat'\n"
        "for i in range(900):\n file.write_text(str(i));time.sleep(.1)\n")
    base=str(Path(getattr(sys,'_base_executable',sys.executable)).resolve())
    p=Profile(work,root,'synthetic-fixture',str(work/'profiles'),'unused.exe',base,root/'unused.dpapi',name)
    b=WindowsBackend(p)
    quote=lambda value:"'"+str(value).replace("'","''")+"'"
    script=work/'Run-Work-Connection.ps1'
    script.write_text("$ErrorActionPreference='Stop'\n$env:PYTHONPATH="+quote(root)+
       "\nSet-Location -LiteralPath "+quote(root)+"\n& "+quote(base)+
       " -m edinburgh_study_agent.work_runtime run --connection-directory "+quote(work)+
       "\nexit $LASTEXITCODE\n",encoding='utf-8-sig')
    report['synthetic_wrapper_sha256']=hashlib.sha256(script.read_bytes()).hexdigest()
    receipt.parent.mkdir(parents=True,exist_ok=True)
    receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    payload=dict(name=name,exe=b.powershell,arguments=b.task_arguments,directory=str(work))
    try:
        result=b.ps("if(Get-ScheduledTask -TaskPath '\\' -TaskName $request.name -ErrorAction SilentlyContinue){throw 'Unique task already exists'}; "
            "$identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name; "
            "$action=New-ScheduledTaskAction -Execute $request.exe -Argument $request.arguments -WorkingDirectory $request.directory; "
            "$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited; "
            "$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew; "
            "Register-ScheduledTask -TaskPath '\\' -TaskName $request.name -Action $action -Principal $principal -Settings $settings|Out-Null; "
            "@{registered=$true;automatic_trigger=$false;current_user=$true;run_level='Limited'}|ConvertTo-Json -Compress",payload)
        registered=bool(result['registered']);report.update(result)
        b.ps("Start-ScheduledTask -TaskPath '\\' -TaskName $request.name",{'name':name})
        deadline=time.monotonic()+20
        pidfile=work/'pids.json';heartbeat=root/'job-heartbeat'
        while time.monotonic()<deadline and (not pidfile.exists() or not heartbeat.exists()):time.sleep(.1)
        if not pidfile.exists() or not heartbeat.exists():raise ValueError('Synthetic scheduled tree did not start')
        pids=json.loads(pidfile.read_text());rows=b.processes()
        wrapper,owner,job=observe_fixture(p,rows,pids,observed)
        report['before']=b.task('inspect')
        b.task('stop')  # Disable only; no Task Scheduler tree-stop.
        stop_supervisor(p,b)
        report['after_owner_stop']=b.task('inspect')
        report['wrapper_absent']=b.process(wrapper.pid) is None
        report['supervisor_absent']=b.process(owner.pid) is None
        report['job_identity_preserved']=b.process(job.pid)==job
        before=heartbeat.stat().st_mtime_ns
        time.sleep(.35)
        report['job_heartbeat_continued']=heartbeat.stat().st_mtime_ns>before
        report['passed']=all(report[key] for key in ('wrapper_absent','supervisor_absent','job_identity_preserved','job_heartbeat_continued'))
    except Exception as error:
        # Fixed diagnostic type/code only; never emit raw scheduler/command data.
        report['error_code']=getattr(error,'code',type(error).__name__)
    finally:
        cleanup_errors=[]
        for item in reversed(observed):
            try:
                if item is not None and b.process(item.pid)==item:b.terminate(item)
            except Exception as error:cleanup_errors.append(getattr(error,'code',type(error).__name__))
        try:
            report['observed_test_processes_absent']=bool(observed) and all(item is None or b.process(item.pid)!=item for item in observed)
        except Exception as error:
            report['observed_test_processes_absent']=False
            cleanup_errors.append(getattr(error,'code',type(error).__name__))
        # Reconcile an uncertain registration once using the same recorded name;
        # never create another task merely because the response was incomplete.
        try:
            owned_task=b.task('inspect')
        except Exception as error:
            owned_task=None
            cleanup_errors.append(getattr(error,'code',type(error).__name__))
        if registered or owned_task:
            try:
                # Reuse the production full task-action/principal check first.
                b.task('inspect')
                removed=b.ps("Unregister-ScheduledTask -TaskPath '\\' -TaskName $request.name -Confirm:$false; "
                     "@{absent= -not [bool](Get-ScheduledTask -TaskPath '\\' -TaskName $request.name -ErrorAction SilentlyContinue)}|ConvertTo-Json -Compress",{'name':name})
                report['test_task_removed']=removed.get('absent') is True
            except Exception as error:cleanup_errors.append(getattr(error,'code',type(error).__name__))
        report['cleanup_errors']=cleanup_errors
        report['passed']=report['passed'] and not cleanup_errors and report.get('test_task_removed',False) and report['observed_test_processes_absent']
        receipt.parent.mkdir(parents=True,exist_ok=True)
        receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-synthetic-scheduler-test',action='store_true',required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.receipt)
    print(json.dumps({key:value for key,value in result.items() if key!='fixture_directory'},ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
