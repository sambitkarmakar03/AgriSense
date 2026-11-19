Read docs/SPEC.md and docs/PROGRESS.md before doing anything. They are the source of truth.
Rules for every task:
- Work only inside the folder named in the task. Never edit another tool's folder.
- Cross-platform: Windows and macOS must both work. Use pathlib / path.join, no bash-only scripts, no hard-coded slashes, no Docker requirement for local dev.
- Keep dependencies minimal. Backend runtime must stay under 400 MB RAM (no torch, no tensorflow in backend/).
- Never commit secrets. Use .env and keep .env.example current.
- Write a plan of at most 15 lines first. Then implement in small commits.
- Run the relevant tests before finishing. If a fix fails twice, stop and report.
- End by appending at most 15 lines to docs/PROGRESS.md: what is done, what is next, known issues.
- Final reply: at most 10 lines.
