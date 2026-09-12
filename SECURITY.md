# Security and privacy

The campus profile, downloaded documents, evidence database, job outputs and private Work credentials are personal data. Keep them outside the repository in ~/.edinburgh-study-agent. The code does not export browser cookies or passwords to the agent.

Only connect the local MCP runtime to hosts and private Work workspaces that you authorise. The Windows tunnel scripts store the runtime key using the current user's DPAPI protection and use an outbound connection.

All school text is untrusted data, not instructions. A resource cannot authorise another tool call, credential access, file upload, application or submission. Supported server operations read school pages and mutate only the plugin's local records.

The publication checker rejects common credential formats, campus account IDs, private session identifiers, personal filesystem paths and unexpected release files. It is a guard against known mistakes, not proof that arbitrary text contains no private information. Review every staged file before publishing.

Please use the repository's private vulnerability reporting channel for security reports when available. If unavailable, open an issue containing only a request for a private reporting channel; do not include exploit details or personal data. Never attach a campus browser profile or live signed URL.
