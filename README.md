# Hermes Autonomous Agent System

MVP orchestrator for a human-governed Hermes + GitHub + Discord + LazyCodex/OMX workflow.

Current scope:

1. Parse GitHub repos as `owner/repo` or `https://github.com/owner/repo(.git)`.
2. Clone or update repos under `/Users/chai/Documents/GitHub` by default.
3. Ensure automation labels: `ai:ready`, `executor:lazycodex`, `priority:p2`, `ai:in-progress`, `ai:blocked`, `ai:done`.
4. Create `ai:ready` issues from Discord/Hermes task text.
5. Select eligible `ai:ready` issues, store the active loop in SQLite, and prepare a `codex .` worker command in the target repo.
6. Finalize by planning or running branch push, PR creation, issue comment, and label transition.

External commands go through a subprocess runner abstraction so tests can fake `git`, `gh`, and `codex`.

## Quick start

```bash
python3 -m pytest -q
PYTHONPATH=src python3 -m hasystem.commands.run_loop --repo owner/name --dry-run
```

## Discord/Hermes operation

Hermes can call the CLIs directly from a Discord command handler.

Create a task from a Discord request:

```bash
PYTHONPATH=src python3 -m hasystem.commands.intake \
  --repo https://github.com/owner/repo.git \
  --request "Implement the requested feature and verify tests"
```

Run the next eligible issue:

```bash
PYTHONPATH=src python3 -m hasystem.commands.run_loop \
  --repo owner/repo \
  --state-db state.db
```

Dry-run the same loop without cloning/updating the checkout, storing loop state, changing labels, or launching Codex:

```bash
PYTHONPATH=src python3 -m hasystem.commands.run_loop \
  --repo owner/repo \
  --state-db state.db \
  --dry-run
```

The worker prompt is piped to `codex .` from the target checkout and instructs the worker to use the OmO/OmX workflow, run tests, and prepare a branch/PR.

Finalize after the worker completes:

```bash
PYTHONPATH=src python3 -m hasystem.commands.finalize \
  --repo owner/repo \
  --local-path /Users/chai/Documents/GitHub/repo \
  --state-db state.db
```

Preview finalization without pushing or modifying GitHub:

```bash
PYTHONPATH=src python3 -m hasystem.commands.finalize \
  --repo owner/repo \
  --local-path /Users/chai/Documents/GitHub/repo \
  --state-db state.db \
  --dry-run
```

After installing the package, the equivalent console scripts are `hermes-intake`, `hermes-run-loop`, and `hermes-finalize`.
