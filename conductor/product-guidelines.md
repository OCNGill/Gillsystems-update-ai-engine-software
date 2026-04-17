# Product Guidelines

## Standards
- Follow current industry best practices for Python agents and automation.
- All scripts must be idempotent — safe to re-run at any point.
- State persistence via JSON/SQLite — no pickle.
- Structured logging (JSON) for every action the agent takes.
- Must work on AMD consumer GPUs (RDNA 2 / RDNA 3) — not just datacenter cards.

## Quality Gates
- Every sub-agent must pass a dry-run mode before live execution.
- All destructive operations (installs, reboots) require explicit confirmation OR are behind the `--yes` flag.
- Version checks must verify SHA/checksum when available.
