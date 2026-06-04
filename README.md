# Hermes Autonomous Agent System

MVP orchestrator for a human-governed Hermes + GitHub + Discord + LazyCodex/OMX workflow.

Current scope:

1. Parse GitHub repos as `owner/repo` or `https://github.com/owner/repo(.git)`.
2. Clone or update repos under `/Users/chai/Documents/GitHub` by default.
3. Ensure automation labels: `ai:ready`, `executor:lazycodex`, `priority:p2`, `ai:in-progress`, `ai:blocked`, `ai:done`.
4. Create `ai:ready` issues from Discord/Hermes task text.
5. Accept a raw Discord/Gateway message, JSON payload, or natural-language request with repo aliases/default repo context and orchestrate intake + run-loop with one command.
6. Select eligible `ai:ready` issues, store the active loop in SQLite, and prepare a `codex .` worker command in the target repo.
7. Finalize by planning or running branch push, PR creation, issue comment, and label transition.

External commands go through a subprocess runner abstraction so tests can fake `git`, `gh`, and `codex`.

## Quick start

```bash
python3 -m pytest -q
PYTHONPATH=src python3 -m hasystem.commands.run_loop --repo owner/name --dry-run
```

## Discord/Hermes operation

Hermes can call the CLIs directly from a Discord command handler.

One-shot Discord/Gateway handler: parse a raw message, clone/update the repo, create the issue, select the ready issue, persist loop state, mark it in progress, and open a Codex worker Terminal session:

```bash
PYTHONPATH=src python3 -m hasystem.commands.discord_request \
  --message '{"repo":"owner/repo","request":"Implement the requested feature and verify tests"}' \
  --state-db state.db
```

Free-form Discord message text also works:

```bash
PYTHONPATH=src python3 -m hasystem.commands.discord_request \
  --message '/agent https://github.com/owner/repo.git Implement the requested feature and verify tests'
```

Natural-language messages can use aliases so Discord feels like talking to a friend instead of filling out a form:

```bash
PYTHONPATH=src python3 -m hasystem.commands.discord_request \
  --repo-alias hermes-autonomous-agent-system=jhun-kim/hermes-autonomous-agent-system \
  --message 'Hermes, hermes-autonomous-agent-system 다음 단계 개발해줘. 자연어 Discord router를 더 좋게 만들어줘.' \
  --dry-run
```

If a Discord channel/thread is dedicated to one repo, configure a default and omit the repo entirely:

```bash
PYTHONPATH=src python3 -m hasystem.commands.discord_request \
  --channel-default-repo 1512060115757432833=jhun-kim/hermes-autonomous-agent-system \
  --thread-id 1512060115757432833 \
  --message 'Hermes, 이 레포에 자동 finalize 붙여줘' \
  --dry-run
```

A global fallback repo is also supported for single-repo workspaces:

```bash
PYTHONPATH=src python3 -m hasystem.commands.discord_request \
  --default-repo jhun-kim/hermes-autonomous-agent-system \
  --message 'Hermes, 다음 단계 진행해줘' \
  --dry-run
```

Dry-run the Discord parser/plan without GitHub, workspace, state, or worker mutations:

```bash
PYTHONPATH=src python3 -m hasystem.commands.discord_request \
  --message 'repo: owner/repo
request: Implement the requested feature and verify tests' \
  --dry-run
```

Create a task from a Discord request without launching the worker loop:

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

After installing the package, the equivalent console scripts are `hermes-discord-request`, `hermes-intake`, `hermes-run-loop`, and `hermes-finalize`.
