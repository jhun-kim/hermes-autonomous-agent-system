# Hermes Autonomous Agent System

MVP orchestrator for a human-governed Hermes + GitHub + Discord + LazyCodex/OMX workflow.

Current scope:

1. Create Python project skeleton.
2. Store loop state in SQLite `state.db`.
3. Select one GitHub issue in dry-run mode using `gh issue list` JSON output.
4. Do not modify GitHub, create branches, create PRs, or send Discord messages yet.

## Quick start

```bash
python -m pytest -q
python -m hasystem.commands.run_once --repo owner/name --dry-run
```
