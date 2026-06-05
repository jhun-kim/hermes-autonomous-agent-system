# Hermes Autonomous Agent System

[![CI](https://github.com/jhun-kim/hermes-autonomous-agent-system/actions/workflows/ci.yml/badge.svg)](https://github.com/jhun-kim/hermes-autonomous-agent-system/actions/workflows/ci.yml)

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

## Operating rule: issue first, code second

When continuing this repo to the next stage, register the intended work as a GitHub issue first, then immediately read/confirm that issue before editing code. The confirmed issue number, title, body, and labels become the source of truth for the work bundle. Only after that confirmation should an agent modify code, docs, tests, branches, or PRs.

This rule is also recorded in `AGENTS.md` so future coding agents see it before making changes.

## Continuous integration

GitHub Actions runs the pytest suite on pushes to `main` and on pull requests using Python 3.11. The CI command is the same local verification command used below: `python3 -m pytest -q`.

## Quick start

```bash
python3 -m pytest -q
PYTHONPATH=src python3 -m hasystem.commands.run_loop --repo owner/name --dry-run
```

## Discord/Hermes operation

Hermes can call the CLIs directly from a Discord command handler.

### Gateway adapter for real Discord/Hermes wiring

For a production Hermes Discord/Gateway tool wrapper, prefer the structured
adapter. It accepts one JSON event envelope on stdin or `--event-json`, routes
the event through `DiscordAutomationService`, and prints one structured JSON
object that a gateway can forward back to Discord or to a tool runtime.

Minimum dry-run event:

```bash
printf '%s\n' '{
  "platform": "discord",
  "guild_id": "123",
  "channel_id": "1512060115757432833",
  "thread_id": "1512060115757432833",
  "sender": {"id": "42", "display_name": "Chai"},
  "content": "Hermes, hasystem integrate the gateway adapter",
  "dry_run": true
}' | PYTHONPATH=src python3 -m hasystem.commands.gateway_adapter \
  --repo-alias hasystem=jhun-kim/hermes-autonomous-agent-system
```

The same payload can be passed with `--event-json`. The output includes
`status`, `repo`, `parsed_request`, `intake`, `loop`, and `hints`. In dry-run
mode, `intake` and `loop` are `null` and Hermes proves the routing decision
without creating issues, changing labels, writing loop state, cloning/updating
repos, or launching workers.

Router config can live in JSON:

```json
{
  "repo_aliases": {
    "hasystem": "jhun-kim/hermes-autonomous-agent-system"
  },
  "channel_default_repos": {
    "1512060115757432833": "jhun-kim/hermes-autonomous-agent-system"
  },
  "allow_repos": ["jhun-kim/hermes-autonomous-agent-system"],
  "default_repo": "jhun-kim/hermes-autonomous-agent-system"
}
```

Use it like this:

```bash
PYTHONPATH=src python3 -m hasystem.commands.gateway_adapter \
  --config hermes-router.json \
  --event-json '{"platform":"discord","channel_id":"1512060115757432833","content":"Hermes, 다음 단계 진행해줘","dry_run":true}'
```

CLI flags override config for aliases, channel/thread defaults, default repo,
and allow-list entries:

```bash
PYTHONPATH=src python3 -m hasystem.commands.gateway_adapter \
  --config hermes-router.json \
  --repo-alias hasystem=jhun-kim/hermes-autonomous-agent-system \
  --channel-default-repo 1512060115757432833=jhun-kim/hermes-autonomous-agent-system \
  --allow-repo jhun-kim/hermes-autonomous-agent-system \
  --dry-run \
  --event-json '{"platform":"discord","content":"Hermes, hasystem run the next task"}'
```

When wiring this into a real Hermes Discord/Gateway workflow:

1. The gateway should send the raw Discord content plus platform, guild,
   channel, thread, and sender fields as the event envelope.
2. Use `dry_run: true` first to verify repo selection in each channel/thread.
3. Remove dry-run only after the channel config and `allow_repos` list are
   correct.
4. Use `no_run_loop: true` or `--no-run-loop` when Hermes should create an
   issue but defer worker launch.
5. Non-dry-run gateway routing fails closed unless config includes `allow_repos`
   or the CLI supplies `--allow-repo`. `--allow-any-repo` exists for trusted
   private gateways only.
6. Start `/restart` or a new Codex session whenever the worker runtime, OmX/OmO
   session routing, environment variables, installed console scripts, or router
   config file path changes. For ordinary new Discord requests in an already
   configured session, a restart is not required; send a new event envelope.

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

The worker prompt is piped to `codex .` from the target checkout and instructs the worker to use the OmO/OmX workflow, specifically use the ulw skill/workflow, run tests, and prepare a branch/PR.

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

After installing the package, the equivalent console scripts are `hermes-discord-request`, `hermes-gateway-adapter`, `hermes-intake`, `hermes-run-loop`, `hermes-run-once`, and `hermes-finalize`.
