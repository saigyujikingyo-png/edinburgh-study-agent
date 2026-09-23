"""Small, dependency-free credential form. No script or external asset requests."""
from html import escape

COPY = {
    "en": {
        "title": "Connect your NMR archive", "subtitle": "Set up once. Ask your agent for the next sample.",
        "password": "NMR password", "username": "NOMAD username", "group": "Teaching group",
        "remember": "Remember this connection", "remember_help": "Encrypted for your Windows account. Remove it any time through your agent.",
        "memory": "This device keeps the connection only until the plugin stops.",
        "consent": "Allow this teaching archive to use HTTP", "consent_help": "The old school archive sends its group password over unencrypted HTTP. Applies to this saved group only.",
        "submit": "Save and connect", "private": "Your password stays out of the conversation.",
        "temporary_done": "Connected for one hour", "temporary_text": "Your request is retained. Return to your agent to continue; this connection was not remembered.",
        "done": "Connection saved", "done_text": "Your request is retained. Return to your agent to continue; future queries reuse this connection.",
        "nomad_done": "Signed in", "nomad_text": "Return to your agent to continue. The session is reused until NOMAD expires it.",
        "unverified": "Archive access is not yet verified; the next query checks it.",
        "error": "Could not connect. Check your details or campus network and try again. Your request is retained.",
        "consent_error": "Select the HTTP permission to connect to this older archive.",
        "authentication": "NOMAD rejected this sign-in. Check your NOMAD username and password. Your request is retained.",
        "vpn_disconnected": "FortiClient VPN is disconnected. Off campus, connect to the University of Edinburgh VPN on this computer, then submit again. Your request is retained.",
        "vpn_active_service_unreachable": "A FortiClient adapter is active, but NOMAD is unreachable. Check the university VPN connection or service, then submit again. Your request is retained.",
        "network_unavailable": "NOMAD is unreachable. Off campus, connect FortiClient to the University of Edinburgh VPN on this computer. Your request is retained.",

        "where": "Use this form on the computer running UoE Companion.",
    },
    "zh": {
        "title": "连接你的 NMR 档案", "subtitle": "填写一次，下次直接让智能体查样本。",
        "password": "NMR 密码", "username": "NOMAD 用户名", "group": "课程组",
        "remember": "记住此连接", "remember_help": "使用当前 Windows 账号加密保存，随时可以让智能体移除。",
        "memory": "此设备仅保留连接至插件进程结束。",
        "consent": "允许此课程档案使用 HTTP", "consent_help": "学校旧档案通过未加密 HTTP 传输课程组密码，仅对此保存的课程组生效。",
        "submit": "保存并连接", "private": "密码不会进入聊天记录。",
        "temporary_done": "已连接，有效期一小时", "temporary_text": "请求已保留，回到智能体即可继续；此次未记住连接。",
        "done": "连接已保存", "done_text": "请求已保留，回到智能体即可继续；之后查询会自动复用连接。",
        "nomad_done": "登录成功", "nomad_text": "回到智能体即可继续。此会话会复用至 NOMAD 要求重新登录。",
        "unverified": "档案访问尚未验证，将在下一次查询时检查。",
        "error": "连接未成功，请检查填写信息或校园网络后重试。请求已保留。",
        "consent_error": "连接旧档案需要勾选 HTTP 使用许可。",
        "authentication": "NOMAD 拒绝了此次登录，请检查 NOMAD 用户名和密码。请求已保留。",
        "vpn_disconnected": "FortiClient VPN 未连接。校外请在这台电脑上连接爱丁堡大学 VPN，再提交。请求已保留。",
        "vpn_active_service_unreachable": "FortiClient 网卡已启用，但 NOMAD 仍不可达。请检查是否连接了学校 VPN，或确认服务状态，再提交。请求已保留。",
        "network_unavailable": "目前无法访问 NOMAD。校外请在这台电脑上使用 FortiClient 连接爱丁堡大学 VPN。请求已保留。",

        "where": "请在运行 UoE Companion 的电脑上使用此表单。",
    },
}

STYLE = """
:root{color-scheme:light dark;--bg:#f0f5f3;--card:#fff;--ink:#173b38;--muted:#526b68;--line:#d8e5e0;--accent:#246f60;--field:#f8faf9}
*{box-sizing:border-box}body{margin:0;min-height:100dvh;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;display:grid;place-items:center;padding:24px 16px}
main{width:min(100%,460px);padding:32px;border:1px solid var(--line);border-radius:24px;background:var(--card);box-shadow:0 20px 65px #153c3010}.brand{display:flex;gap:10px;align-items:center;font-size:14px;font-weight:650;margin-bottom:26px}.mark{display:grid;place-items:center;width:34px;height:34px;border-radius:11px;background:var(--accent);color:white;font-size:20px}
h1{font-size:25px;line-height:1.25;letter-spacing:-.5px;margin:0 0 10px}.muted,small{color:var(--muted)}p{margin:0 0 22px}.badge{display:inline-block;border:1px solid var(--line);border-radius:9px;padding:6px 12px;margin-bottom:18px;font-size:13px}
label.field{display:block;font-size:14px;font-weight:600;margin-bottom:17px}input:not([type=checkbox]):not([type=hidden]){display:block;width:100%;border:1px solid var(--line);border-radius:10px;padding:11px 13px;margin-top:7px;background:var(--field);color:var(--ink);font:inherit;min-height:46px}input:focus-visible,button:focus-visible{outline:3px solid #7fc3b2;outline-offset:2px}
.check{display:flex;gap:10px;align-items:flex-start;margin:17px 0 4px;font-size:14px}input[type=checkbox]{accent-color:var(--accent);margin:4px 0 0;width:17px;height:17px;flex:none}small{display:block;font-size:12px;line-height:1.5;margin-left:27px}.notice{border-radius:10px;background:var(--field);padding:12px 14px;margin:18px 0;font-size:13px}.error{border:1px solid #c87663;color:var(--ink)}button{cursor:pointer;display:block;width:100%;margin-top:24px;padding:12px;border:0;border-radius:11px;background:var(--accent);color:white;font:600 15px system-ui;min-height:46px}button:hover{filter:brightness(1.06)}footer{font-size:12px;color:var(--muted);margin-top:20px;text-align:center}.success{font-size:30px;color:var(--accent);margin-bottom:14px}
@media(prefers-color-scheme:dark){:root{--bg:#101c1a;--card:#182926;--ink:#e3f3ed;--muted:#adc5bc;--line:#334b43;--accent:#377e6b;--field:#20352f}}
@media(max-width:420px){main{padding:24px}h1{font-size:23px}}
"""


def render(panel, *, error=False, complete=False, locale="en", persistent=False):
    language = "zh" if locale.startswith("zh") else "en"
    c = COPY[language]
    legacy = panel.provider == "legacy"
    content = '<div class="brand"><span class="mark" aria-hidden="true">U</span>UoE Companion</div>'
    if complete:
        title = "nomad_done" if not legacy else "done" if panel.remembered else "temporary_done"
        description = "nomad_text" if not legacy else "done_text" if panel.remembered else "temporary_text"
        content += (f'<div class="success" aria-hidden="true">✓</div><h1>{c[title]}</h1>'
                    f'<p class="muted">{c[description]}</p>')
        if legacy:
            content += f'<div class="notice">{c["unverified"]}</div>'
    else:
        content += f'<h1>{c["title"]}</h1><p class="muted">{c["subtitle"]}</p>'
        content += f'<span class="badge">{c["group"]}: {escape(panel.group)}</span>' if legacy else '<span class="badge">NOMAD</span>'
        if error:
            key = "consent_error" if error == "consent" else error if isinstance(error, str) and error in c else "error"
            content += f'<div class="notice error" role="alert">{c[key]}</div>'
        content += f'<form method="post" action="{panel.path}"><input type="hidden" name="nonce" value="{panel.nonce}">'
        if not legacy:
            content += f'<label class="field">{c["username"]}<input name="username" autocomplete="username" maxlength="128" required></label>'
        content += f'<label class="field">{c["password"]}<input name="password" type="password" autocomplete="current-password" maxlength="1024" required autofocus></label>'
        if legacy:
            if persistent:
                content += (f'<label class="check"><input type="checkbox" name="remember" value="yes" checked><span>{c["remember"]}</span></label>'
                            f'<small>{c["remember_help"]}</small>')
            else:
                content += f'<div class="notice">{c["memory"]}</div>'
            checked = ' checked' if panel.http_approved else ''
            content += (f'<label class="check"><input type="checkbox" name="http_consent" value="yes" required{checked}><span>{c["consent"]}</span></label>'
                        f'<small>{c["consent_help"]}</small>')
        content += f'<button type="submit">{c["submit"]}</button></form><footer>{c["private"]}<br>{c["where"]}</footer>'
    return (f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>UoE Companion · NMR</title><style>{STYLE}</style></head><body><main>{content}</main></body></html>')
