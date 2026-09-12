# Host setup and compatibility

The MCP server uses stdio and owns a dedicated persistent school browser. No host browser, screenshots or coordinate clicks are needed for normal operation.

## Local MCP hosts

Install the project in a dedicated Python environment and configure a single MCP entry to run `python -m edinburgh_study_agent.server`. The bundled installer creates a private runtime and host-local .mcp.json.

Use the workflow in skills/edinburgh-study/SKILL.md. Never replace a host's complete MCP configuration to add this plugin. After updating a local Codex plugin, a new Codex development conversation loads its new skill and tool metadata. This is separate from Work usage.

For another account, set EDINBURGH_STUDY_HOME to a different private local directory. Use a separate browser profile and database for that account. Do not share campus profiles or automatically mix account records.

## ChatGPT Work

Codex develops and packages this project. ChatGPT Work is the intended user environment.

Connect Work to this computer through the authorised private Secure MCP Tunnel described in WORK_SETUP.md. This has been tested in an existing Work conversation. Work's own cloud browser and Codex's local marketplace are separate from this connection.

The computer must be on, signed in and online. The logon task maintains the connection, not periodic school scraping. Credentials remain inside the plugin-owned browser; the server may use the user's own observed EUCLID account identifier for documented campus SSO discovery.

## Persistence

The private data directory contains evidence, downloads, collections, tasks, exported calendars, job results and the school profile. It is excluded from release archives and survives reinstall.

The plugin does not send telemetry. Content returned to Work is subject to the host's normal retention. Downloads stay on this computer; Work can read their supported text through MCP, and a local path is not a cloud attachment.

Official school records and submissions are never modified by these tools.
