# UoE Companion contributor entrypoint

Read DEVELOPMENT_PRINCIPLES.md (shared rule version 2026-09-13.1), CONTRIBUTING.md and CODEX_CLOUD.md before development. These are the shared Chembridge defaults plus this product's account, source and verification constraints. New user instructions take precedence.

Keep one product identity and shared core across ChatGPT Chat, local Work, cloud Work, Codex and other suitable agents. Codex is both a development tool and an end-user host. Use public English documentation, explicit open-source licensing, accessible installation, Terra max benchmarking and bounded resource and quota use. Target support is not acceptance evidence.

Use synthetic data for cloud tests. Do not copy campus sessions, private coursework, tokens or local browser profiles into source or cloud containers. Preserve user files, other plugins and unrelated working state. Retain the source and account boundaries in CONTRIBUTING.md, SECURITY.md and actual acceptance records.

## Chembridge cloud development

The shared umbrella entrypoint is https://github.com/saigyujikingyo-png/chembridge. Read the current included DEVELOPMENT_PRINCIPLES.md and CODEX_CLOUD.md. Use `bash scripts/setup_codex_cloud.sh` from this repository root for setup and cached-container maintenance. Each product task remains independent; do not automatically relay messages or status between Origin, ChemDraw and other tasks.

Cloud configuration, portable checks, native execution, model/host acceptance and artifact delivery are separate gates. The known OpenAI local Work project-sync frontend bug remains out of scope; do not repair application caches, registrations or internals for that issue.
