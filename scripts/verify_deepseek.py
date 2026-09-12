"""Probe the published official DeepSeek MCP bridge, without a model/account or campus login.

Install @deepseek-ai/dsh-mcp-client in an isolated directory first. This script uses
its real transport, config resolver, discovery, executor and text renderer, with a
small registration/lifecycle fixture. It does NOT run a full Harness agent turn.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from edinburgh_study_agent.hosts import server_config, host_document

PROBE = r'''import fs from 'node:fs';
import assert from 'node:assert/strict';
import * as bridge from '@deepseek-ai/dsh-mcp-client';
import { assertObjectJsonSchema } from '@deepseek-ai/dsh-tools';
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const definitions=new Map(), disposers=[];
// This fixture is NOT a DeepSeek model, agent loop or policy system.
const ctx={root:{},logger:{info(){},error(message){throw Error(message)}},
  tools:{register(def){assertObjectJsonSchema(def.parameters);definitions.set(def.name,def);return ()=>definitions.delete(def.name)}},
  effect(callback){const dispose=callback();if(dispose)disposers.push(dispose)}};
const config=bridge.Config({...input[0].insert[0].config,failOnStartupError:true});
const call=async(name,args)=>{
  const def=definitions.get('mcp__uoe-companion__'+name);assert.ok(def,name);
  const value=await def.execute(args,{signal:AbortSignal.timeout(30000)});
  const rendered=def.output.render(args,value);
  assert.equal(rendered[0].type,'text');
  assert.deepEqual(JSON.parse(rendered[0].text),value.structuredContent);
  return value.structuredContent;
};
try {
  await bridge.apply(ctx,config);
  assert.equal(definitions.size,28);
  assert.ok(!definitions.has('mcp__uoe-companion__study_capture'));
  const status=await call('study_status',{});
  assert.equal(status.name,'UoE Companion');
  const directory=await call('study_services',{query:'bibliotheque',locale:'fr-FR'});
  assert.equal(directory.services[0].id,'library');
  assert.equal(directory.services[0].title,'Bibliothèque');
  const settings=await call('study_preferences',{locale:'ar',display_timezone:'Asia/Tokyo'});
  assert.equal(settings.presentation.direction,'rtl');
  const task=await call('study_task_create',{title:'Synthetic bridge task',estimate_minutes:25,due_date:'2030-01-07'});
  const agenda=await call('study_agenda',{start:'2030-01-07',end:'2030-01-07'});
  assert.equal(agenda.items[0].id,task.id);
  assert.equal(agenda.items[0].timing,'date_only');
  assert.equal(agenda.presentation.display_timezone,'Asia/Tokyo');
  await call('study_task_update',{task_id:task.id,status:'done'});
  const after=await call('study_agenda',{start:'2030-01-07',end:'2030-01-07'});
  assert.equal(after.total_matches,0);
  let rejected=false;try{await call('study_agenda',{start:'2030-01-08',end:'2030-01-07'})}catch{rejected=true}
  assert.ok(rejected);
  rejected=false;try{await call('study_task_create',{title:'Invalid estimate',estimate_minutes:1})}catch{rejected=true}
  assert.ok(rejected);
  console.log(JSON.stringify({passed:true,version:status.version,tools:definitions.size,
    official_bridge:'config/discovery/execute/text projection',input_schemas:'accepted by official dsh-tools',
    multilingual_catalog:true,local_task_agenda_roundtrip:true,errors_propagated:true,
    fixture:'isolated synthetic data and registration/lifecycle fixture',full_deepseek_agent_turn:'not_tested'}));
} finally { for(const dispose of disposers.reverse())await dispose(); }
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-modules",required=True,type=Path)
    parser.add_argument("--python",type=Path,default=Path(sys.executable))
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    node=shutil.which("node")
    if not node:
        parser.error("Node is required for this optional development probe.")
    package=json.loads((args.node_modules/"@deepseek-ai/dsh-mcp-client/package.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="uoe-probe-",dir=args.node_modules.parent) as temporary:
        folder=Path(temporary)
        (folder/"probe.mjs").write_text(PROBE,encoding="utf-8")
        config=host_document("deepseek-harness",server_config(args.python,folder/"campus"))
        (folder/"config.json").write_text(json.dumps(config),encoding="utf-8")
        child=subprocess.run([node,str(folder/"probe.mjs"),str(folder/"config.json")],capture_output=True,text=True,
                             encoding="utf-8",timeout=55,env={**os.environ,"PYTHONUTF8":"1"})
        if child.returncode:
            raise RuntimeError(child.stderr[-6000:])
        result=json.loads(child.stdout.strip().splitlines()[-1])
        result["bridge_package_version"]=package["version"]
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result))

if __name__=="__main__":
    main()
