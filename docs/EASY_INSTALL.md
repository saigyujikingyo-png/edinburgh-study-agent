# Easy installation — 0.8.1 student preview

## Windows x64

Download the Windows setup ZIP from the [0.8.1 release](https://github.com/saigyujikingyo-png/edinburgh-study-agent/releases/tag/v0.8.1), extract the whole archive, and double-click **Install.cmd**. Keep the `payload` folder beside it.

The setup page runs temporarily on this computer's loopback interface. Its private URL is random, external origins are rejected, and no page assets or installation data are sent to a hosted setup service. Select English or Chinese, choose a local agent, and click **Install / update**. Select **Finish** to stop the helper; an abandoned idle helper also expires.

The bundle includes Python and plugin dependencies. You do not need to install Python, Git or a development environment. Google Chrome or Microsoft Edge must already be available. The installer does not install a browser, change system Python, request administrator privileges or start a permanent setup server.

### Agent connections

| Agent | Setup behaviour |
| --- | --- |
| WorkBuddy | Merge one managed UoE entry with the daily tool profile, preserving unrelated entries and custom settings; reload MCP afterwards |
| Claude Desktop | Same local configuration merge and backup; reload the application afterwards |
| ChatGPT Chat / local Work / cloud Work | Preserve an existing private connection. New users must complete the platform/account setup in [WORK_SETUP.md](WORK_SETUP.md); account privileges cannot be supplied by this installer |
| DeepSeek Harness | Generate a private overlay; import it through an existing Harness installation containing its official MCP client |
| Claude Code / Codex / generic MCP | Generate a private MCP document and follow the [host guide](HOSTS.md). No source checkout is required for normal use |

Configuration files are written under the private data directory's `connections` folder. They contain local paths, not school credentials. Each person needs their own private connection and campus login. All clients use the same execution core and data directory on that person's computer.

After installation, reload the agent connection and ask for a status check. Sign in only when required, through the wizard's school sign-in button or the agent's `study_connect_school` tool. Password and MFA are entered on the University page. A protocol check does not confirm campus login or a host model's behaviour.

## Updates and recovery

Run the new setup ZIP and use the same private directory. The installer verifies every manifest file and tests the candidate runtime with isolated data before replacing the old runtime. Host configuration changes receive exact backups. A failed check or configuration merge rolls back the runtime and changes made in that installation attempt.

If the existing runtime is in use, installation stops without killing agents. Finish current school jobs and close/reload the UoE MCP connection in local clients. For an existing ChatGPT deployment, pause its managed Work connection before upgrading and resume it afterwards using the existing private connection controls. No new campus login or replacement ChatGPT entry is required.

The previous runtime is retained as `runtime-backup-<timestamp>`; its location is recorded in `installation.json`. Repeating the same installation verifies the files and connection without replacing a healthy identical runtime. Local school profiles, downloads, collections, tasks, account association and tunnel credentials are preserved.

If a bundle is incomplete or a checksum fails, obtain a fresh copy from the release. The installer does not silently run partially copied components. If a client configuration is invalid or an unrelated server owns the same name, it reports the conflict and preserves that file. The source installer remains a developer recovery route.

## Removal

Remove the UoE connection from the chosen host's normal MCP/plugin settings. For an existing ChatGPT deployment, stop its managed connection first. Keeping the private data directory preserves school login, downloads and tasks for a later reinstall. Removing the extracted setup folder removes only the installer, not the installed backend or private data. Automated removal of user data is deliberately not part of this installer.

## Known limits

- Windows x64 is the bundled platform. Live school access on other operating systems and Windows ARM is unverified.
- The wizard is bilingual; the ten-language catalog applies to agent workflows, not every setup label.
- New ChatGPT account/tunnel registration and some other host-specific imports are still personal setup steps.
- University session expiry/MFA and provider changes can require user action.
- Cloud Work depends on this computer being online. Downloads are local; host attachment delivery is separate.
- A second student's own account and real 0.7.2 model conversations across all hosts have not been certified.
