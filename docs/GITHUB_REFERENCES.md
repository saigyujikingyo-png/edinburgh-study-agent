# GitHub reference review

Reviewed on 2026-09-12. These are primary project sources, not a claim that another project's adapters work with the current Edinburgh deployment.

| Source | What was checked | Decision for this project |
| --- | --- | --- |
| [BlackboardSync](https://github.com/sanjacob/BlackboardSync/tree/1de682ffa714ca3a22014d8af08c5b03d11aa70e) | README, supported-university list, license and sync/download modules at the pinned commit; Edinburgh appears in the list | Useful reference for incremental download scheduling, recursive content and cancellation. Keep our independent implementation; no source copied or new dependency added |
| [bblearn](https://github.com/sanjacob/bblearn) | README and documented session-based Learn API client | Candidate for a separately reviewed API adapter; not used by the current plugin |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | Official SDK and MIT license | Existing dependency for host-neutral typed tools and the stdio protocol |
| [Playwright Python](https://github.com/microsoft/playwright-python) | Official project and Apache-2.0 license | Existing dependency for the plugin-owned persistent browser and structural DOM access |
| [Blackboard developer documentation](https://github.com/blackboard/anthologydevdocs) | Official [REST application prerequisites](https://docs.blackboard.com/docs/blackboard/rest-apis/getting-started/framework) | An application-key integration requires university-side enablement; do not present this as already available to a student |

BlackboardSync's source headers at the pinned revision specify GPL version 2 or later. Its README labels the project GPL v2. bblearn's README also identifies GPL v2. Neither project's code is included in this MIT project. This review records behavior and compatibility decisions, not a license conversion.

## Follow-up priorities

1. Compare content freshness metadata before transferring unchanged files. A checksum validates a local file; it alone cannot prove the remote file is still current.
2. Preserve per-file progress and cancellation for larger course downloads without calling an interrupted run complete.
3. Expand Timetabler into structured events using supported, observed data or a user-provided export. Do not infer actual events from an overall activity count.
4. Add provider-specific vacancy and event extraction with explicit pagination and completeness.
5. Consider a documented API integration only after verifying its actual access requirements and license compatibility.

These are future priorities. Version 0.3.0 still uses its dedicated Learn adapter and bounded official-page readers; it does not automatically run periodic school syncs.
