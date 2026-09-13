"""Temporary loopback-only installation wizard; no extra web framework or daemon."""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
import webbrowser

PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UoE Companion setup</title><style>
:root{font-family:system-ui,sans-serif;color:#173c43;background:#f4f6f4}body{max-width:760px;margin:48px auto;padding:0 22px}h1{font-size:32px;margin-bottom:8px}.card{background:white;border:1px solid #d8e3df;border-radius:18px;padding:24px;margin:20px 0}p{line-height:1.65}.muted{color:#526b70}label{display:block;margin:16px 0}input[type=checkbox]{width:18px;height:18px;vertical-align:middle;margin-right:8px}button,a.button{background:#215e64;color:white;border:0;border-radius:9px;padding:12px 18px;font:inherit;cursor:pointer;display:inline-block;text-decoration:none;margin:6px 6px 6px 0}button:disabled{opacity:.45;cursor:wait}button.secondary{background:#e7eeeb;color:#173c43}select,input[type=text]{font:inherit;padding:9px;border:1px solid #acbfba;border-radius:6px}input[type=text]{width:95%}#progress{white-space:pre-wrap;line-height:1.6}#error{color:#9a2630;white-space:pre-wrap}.tag{background:#e4eee8;border-radius:6px;padding:4px 8px}.row{display:flex;align-items:center;justify-content:space-between}small{line-height:1.6;display:block}a{color:#205e65}details{margin-top:20px}
</style><div class="row"><span class="tag">UoE Companion · __VERSION__</span><select id="language" aria-label="Language"><option value="en">English</option><option value="zh">中文</option></select></div>
<h1 data-i18n="title">Your campus, in your agent.</h1><p class="muted" data-i18n="intro">Install once, choose your agent, then sign in to the University. Python and plugin dependencies are included.</p>
<section class="card"><h2 data-i18n="choose">1. Choose your agent</h2>
<label><input type="checkbox" name="host" value="workbuddy">WorkBuddy</label><label><input type="checkbox" name="host" value="claude-desktop">Claude Desktop</label>
<p data-i18n="others">ChatGPT Chat / local Work / cloud Work share one private connection. Existing connections are preserved. For a new account, finish the platform connection step after installation.</p>
<p id="detected" class="muted"></p><small data-i18n="more">For DeepSeek Harness, Claude Code, Codex and other MCP agents, installation generates private connection files and a setup guide.</small>
<details><summary data-i18n="location">Installation location</summary><input id="home" type="text" aria-label="Private installation directory"><small data-i18n="private">Your school login, downloads and tasks stay in your private directory.</small></details>
<button id="install" data-i18n="install">Install / update</button><p id="progress" aria-live="polite"></p><p id="error" role="alert"></p></section>
<section class="card"><h2 data-i18n="connect">2. Connect and sign in</h2><p data-i18n="reload">Reload your agent's MCP connection after installation. The daily tool menu is enabled for the selected local agents.</p>
<button id="login" disabled data-i18n="login">Sign in to the University</button><a class="button" href="https://github.com/saigyujikingyo-png/edinburgh-study-agent/blob/v__VERSION__/docs/WORK_SETUP.md" target="_blank" rel="noreferrer" data-i18n="work">ChatGPT connection guide</a>
<a href="https://github.com/saigyujikingyo-png/edinburgh-study-agent/blob/v__VERSION__/docs/HOSTS.md" target="_blank" rel="noreferrer" data-i18n="guide">Other agent setup</a>
<p data-i18n="credentials">Enter your password and MFA only on the University's sign-in page. If you already signed in, keep using the saved session.</p><p id="complete" class="muted"></p></section>
<small data-i18n="limits">Independent student preview, not a University product. ChatGPT account permissions and school MFA remain personal steps. The campus computer must stay online for cloud Work. This setup window is local and closes its helper when you select Finish.</small><button id="close" class="secondary" data-i18n="finish">Finish</button>
<script>
const zh={title:'在智能体内管理校园事务',intro:'安装一次，选择智能体，再登录学校。安装包已包含 Python 和插件依赖。',choose:'1. 选择智能体',others:'ChatGPT 聊天、本地 Work 和云端 Work 共用一个私有连接。已有连接会保留；新账号需要在安装后完成平台连接授权。',more:'DeepSeek Harness、Claude Code、Codex 等 MCP 智能体可使用安装器生成的私有配置文件和接入说明。',location:'安装位置',private:'校园登录、下载资料和待办保留在你的私有目录内。',install:'安装 / 更新',connect:'2. 连接并登录',reload:'安装后刷新智能体的 MCP 连接。已选择的本地智能体将使用精简日常工具目录。',login:'登录学校',work:'ChatGPT 连接说明',guide:'其他智能体接入',credentials:'密码和 MFA 只填在学校登录页面。已经登录过时，继续复用原会话即可。',limits:'独立学生预览版，非学校官方产品。ChatGPT 账号授权与校园 MFA 仍需本人操作；云端 Work 需要校园后台电脑在线。点击“完成”会关闭本地安装助手。',finish:'完成'};
const en={};document.querySelectorAll('[data-i18n]').forEach(e=>en[e.dataset.i18n]=e.textContent);
function language(){const dict=document.querySelector('#language').value==='zh'?zh:en;document.querySelectorAll('[data-i18n]').forEach(e=>e.textContent=dict[e.dataset.i18n])}
if(navigator.language.startsWith('zh'))document.querySelector('#language').value='zh';language();document.querySelector('#language').onchange=language;
let finished=false;async function api(action,data){const response=await fetch('./'+action,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});const value=await response.json();if(!response.ok)throw Error(value.error||'Setup request failed');return value}
function showError(e){document.querySelector('#error').textContent=e.message}
api('inspect').then(value=>{document.querySelector('#home').value=value.home;for(const [name,found]of Object.entries(value.hosts))document.querySelector('input[value="'+name+'"]').checked=found;document.querySelector('#detected').textContent=value.chatgpt_connection_present?'Existing ChatGPT connection found / 已发现现有 ChatGPT 连接':'';document.querySelector('#login').disabled=!value.runtime_present}).catch(showError);
document.querySelector('#install').onclick=async()=>{document.querySelector('#error').textContent='';document.querySelector('#install').disabled=true;try{await api('install',{home:document.querySelector('#home').value,hosts:[...document.querySelectorAll('input[name=host]:checked')].map(x=>x.value)});poll()}catch(e){showError(e);document.querySelector('#install').disabled=false}};
async function poll(){try{const value=await api('state');document.querySelector('#progress').textContent=value.progress||'';if(value.state==='running'){setTimeout(poll,700);return}document.querySelector('#install').disabled=false;if(value.error)showError(Error(value.error));if(value.state==='complete'){document.querySelector('#login').disabled=false;document.querySelector('#complete').textContent='Installed '+value.version+' · '+value.tools+' daily tools. Configuration files: '+value.connections}}catch(e){showError(e);document.querySelector('#install').disabled=false}}
document.querySelector('#login').onclick=async()=>{document.querySelector('#login').disabled=true;try{await api('login',{home:document.querySelector('#home').value});document.querySelector('#complete').textContent='The dedicated school sign-in window will open. Finish sign-in there, then return to your agent. / 请在专属窗口完成校园登录，再回到智能体。'}catch(e){showError(e)}finally{document.querySelector('#login').disabled=false}};
document.querySelector('#close').onclick=async()=>{try{await api('close',{});finished=true;document.body.textContent='Setup closed. You can close this tab. / 安装助手已关闭，可以关闭此标签页。'}catch(e){showError(e)}};
</script></html>'''


class Wizard:
    def __init__(self, bundle, home):
        self.bundle, self.home = Path(bundle).resolve(), Path(home).resolve()
        self.token = secrets.token_urlsafe(32)
        self.state = {"state": "idle"}
        self.lock = threading.Lock()
        self.last_request = time.monotonic()

    def start_install(self, data):
        from .setup_core import install
        with self.lock:
            if self.state["state"] == "running":
                raise ValueError("Installation is already running.")
            if not isinstance(data.get("hosts"), list) or any(not isinstance(h, str) for h in data["hosts"]):
                raise ValueError("Choose an agent from the list.")
            target = Path(data.get("home", str(self.home))).resolve()
            self.state = {"state": "running", "progress": "Starting installation"}

        def work():
            try:
                value = install(self.bundle, target, data["hosts"],
                                progress=lambda p: self.state.update(progress=p))
                self.home = target
                self.state.update(state="complete", version=value["version"], tools=value["check"]["tools"],
                                  connections=value["connection_documents"])
            except Exception as exc:
                self.state.update(state="failed", error=str(exc))
        threading.Thread(target=work, daemon=True).start()


def make_server(wizard, port=0):
    from . import __version__

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # The local access URL and private paths must not enter logs.

        def respond(self, status, data, mime="application/json"):
            raw = data.encode("utf-8") if isinstance(data, str) else json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != origin.removeprefix("http://"):
                return False
            if self.headers.get("Origin") not in (None, origin):
                return False
            return self.path.startswith("/" + wizard.token + "/")

        def do_GET(self):
            if not self.allowed():
                self.respond(403, {"error": "Open the private setup link from Install.cmd."}); return
            wizard.last_request = time.monotonic()
            action = self.path.rsplit("/", 1)[-1]
            if action == "":
                self.respond(200, PAGE.replace("__VERSION__", __version__), "text/html")
            elif action == "inspect":
                from .setup_core import inspect
                self.respond(200, inspect(wizard.home))
            elif action == "state":
                self.respond(200, wizard.state)
            else:
                self.respond(404, {"error": "Unknown setup operation."})

        def do_POST(self):
            if not self.allowed() or self.headers.get("Content-Type") != "application/json":
                self.respond(403, {"error": "Use the local setup page."}); return
            wizard.last_request = time.monotonic()
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError("Invalid setup request size.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Invalid setup request.")
                action = self.path.rsplit("/", 1)[-1]
                if action == "install":
                    wizard.start_install(data)
                elif action == "login":
                    python = wizard.home / "runtime/Scripts/python.exe"
                    if not python.is_file() or Path(data.get("home", str(wizard.home))).resolve() != wizard.home:
                        raise ValueError("Complete installation at this location before signing in.")
                    # Only our fixed installed module is executed, with an argument vector.
                    completed = subprocess.run([str(python), "-m", "edinburgh_study_agent.setup_core", "login", "--home", str(wizard.home)],
                        capture_output=True, text=True, encoding="utf-8", timeout=15,
                        creationflags=0x08000000 if os.name == "nt" else 0)
                    if completed.returncode:
                        raise ValueError("The login helper did not start. Use 'connect school' in your agent.")
                elif action == "close":
                    if wizard.state["state"] == "running":
                        raise ValueError("Wait for installation to finish before closing.")
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    raise ValueError("Unknown setup operation.")
                self.respond(200, {"accepted": True})
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.respond(400, {"error": str(exc)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--home", type=Path, default=Path.home() / ".edinburgh-study-agent")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    wizard = Wizard(args.bundle, args.home)
    server = make_server(wizard)
    url = f"http://127.0.0.1:{server.server_port}/{wizard.token}/"
    if args.no_open:
        print(url, flush=True)
    else:
        webbrowser.open(url)
    def idle_shutdown():
        while True:
            time.sleep(30)
            if wizard.state["state"] != "running" and time.monotonic() - wizard.last_request > 1800:
                server.shutdown(); return
    threading.Thread(target=idle_shutdown, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
