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

### Reusable installed gateway wrapper example

This repository includes an adaptable production wiring example:

- `examples/hermes-router.json` — repo aliases, channel/thread default repo routing,
  `default_repo`, and a fail-closed `allow_repos` list.
- `examples/hermes-gateway-event.dry-run.json` — a minimal Discord event envelope
  that can be piped into the adapter while validating routing.
- `scripts/hermes-gateway-wrapper` — a small shell wrapper around the installed
  `hermes-gateway-adapter` console command.

Dry-run the installed console command directly:

```bash
hermes-gateway-adapter \
  --config examples/hermes-router.json \
  --event-json "$(cat examples/hermes-gateway-event.dry-run.json)"
```

Dry-run through the reusable wrapper; this is the safest mode to wire into a
Hermes Discord gateway first because it proves channel/thread routing without
creating issues, mutating labels, writing loop state, cloning repos, or launching
workers:

```bash
scripts/hermes-gateway-wrapper --dry-run \
  --event-json "$(cat examples/hermes-gateway-event.dry-run.json)"
```

After dry-run output selects the expected repo, send a live event by removing
`dry_run: true` from the event JSON and using live mode:

```bash
jq '.dry_run = false' examples/hermes-gateway-event.dry-run.json | \
  scripts/hermes-gateway-wrapper --live
```

Live mode deliberately does **not** pass `--allow-any-repo`. Non-dry-run routing
therefore stays fail-closed: the selected repository must appear in
`allow_repos` inside `examples/hermes-router.json`, or the deployment must pass
an explicit `--allow-repo owner/repo` adapter argument. Use `--allow-any-repo`
only for a trusted private gateway after reviewing the routing boundary.

Before deploying the wrapper in a real Hermes Discord gateway, run the isolated
live-mode fixture. It replaces the installed adapter with a fake executable, so
it verifies wrapper `--live` allow-list behavior without touching GitHub,
cloning repos, writing real loop state, or launching Codex/OmX workers:

```bash
python3 -m pytest -q tests/test_gateway_wrapper_live_fixture.py
```

#### Hermes context-compression runtime hook

`hermes-context-compression-hook` accepts the JSON shape produced by a live
Hermes compression lifecycle boundary after `_compress_context` rotates from an
old session id to a new one. It is disabled by default; production runtimes must
explicitly opt in:

```bash
export HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED=true
```

The hook reads JSON from `--event-json` or stdin and routes Discord compression
records through the same hasystem `context.compaction` gateway seam used by the
rollover adapter. Non-Discord sessions and disabled/default runs are explicit
no-ops.

Low-threshold smoke for a real runtime-shaped lifecycle event:

```bash
PYTHONPATH=src HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED=true \
  python3 -m hasystem.commands.context_compression_hook \
  --compaction-rollover-threshold 1 \
  --event-json '{
    "platform": "discord",
    "discord": {"guild_id": "guild", "channel_id": "channel", "thread_id": "thread"},
    "session": {"old_id": "old-session", "new_id": "new-session"},
    "repository": "jhun-kim/hermes-autonomous-agent-system",
    "latest_goal": "continue the active issue",
    "active_issue": {"number": 25, "title": "Connect live hook", "labels": ["ai:in-progress"]},
    "compression": {"summary": "compressed transcript summary", "handoff_context": "runtime hook handoff"}
  }'
```

#### Real gateway deployment checklist

Use this checklist before pointing a production Hermes Discord gateway at
`scripts/hermes-gateway-wrapper` or an adapted copy:

1. Copy the wrapper beside the gateway runtime, or keep this repository checkout
   as a read-only deployment dependency, and set the wrapper's `--config` path to
   the deployed router JSON location rather than a developer-local path.
2. Validate channel/thread routing in dry-run mode with
   `examples/hermes-gateway-event.dry-run.json`; confirm the selected `repo`,
   `status`, and `hints` are what the gateway should report to Discord.
3. Run the isolated live-mode fixture before enabling live Discord events:
   `python3 -m pytest -q tests/test_gateway_wrapper_live_fixture.py`.
4. Review the fail-closed repository boundary. Keep production repos in
   `allow_repos` or pass explicit `--allow-repo owner/repo` entries; do not use
   `--allow-any-repo` by default.
5. Restart only at runtime boundaries: use `/restart` or restart the gateway
   process after changing the installed wrapper/adapter, OmX/OmO worker runtime,
   environment variables, or router config file path. Ordinary new Discord
   requests in an already configured runtime do not require restart.
6. Keep a rollback note with the previous wrapper path, router config path, and
   adapter version so rollback is a config/path revert plus the same restart
   boundary from step 5.

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

#### GODMODE safe gateway configuration and issue #33 smoke

GODMODE is fail-closed. A `godmode`, `godmode status`, `godmode pause`,
`godmode resume`, or `godmode stop` command is accepted only when the Discord
thread/channel or sender appears in the router config `godmode` authorization
lists. The tracked `examples/hermes-router.json` keeps the originating issue #33
thread, `1512332564218773564`, authorized for smoke testing while using safe
runtime guardrails:

```json
{
  "godmode": {
    "authorized_channel_ids": ["1512332564218773564"],
    "authorized_sender_ids": ["REPLACE_WITH_TRUSTED_DISCORD_USER_ID"],
    "max_iterations": 0,
    "max_runtime_seconds": 60,
    "max_failures": 1,
    "create_issue_when_empty": false,
    "seed_issue_labels": ["ai:ready", "executor:lazycodex", "priority:p2"]
  }
}
```

Safe defaults for first deployment:

1. Keep `max_iterations: 0` and `create_issue_when_empty: false` until status
   and authorization checks pass in the live Discord gateway.
2. Replace `REPLACE_WITH_TRUSTED_DISCORD_USER_ID` with the trusted operator's
   Discord user id before relying on sender-based authorization. Keep the
   channel/thread allow-list narrow even when sender authorization is present.
3. Keep `allow_repos` fail-closed. Do not use `--allow-any-repo` for GODMODE.
4. Use an isolated `--state-db` and `--workspace` path for each smoke. Do not
   use the repository root `state.db` for smoke tests.
5. Treat issue bodies as untrusted task data. The worker prompt preserves the
   repository issue-first and OmO/OmX ULW workflow rules.

Controlled local/live status smoke for the originating thread; this creates only
an isolated smoke DB, reports stopped status, and does not clone a workspace or
launch a worker because `godmode status` is a read/control command and
`max_iterations` is `0`:

```bash
SMOKE_ROOT="$(mktemp -d /tmp/hermes-godmode-smoke.XXXXXX)"
PYTHONPATH=src python3 -m hasystem.commands.gateway_adapter \
  --config examples/hermes-router.json \
  --event-json "$(cat examples/hermes-godmode-status-smoke.discord-event.json)" \
  --state-db "$SMOKE_ROOT/state.db" \
  --workspace "$SMOKE_ROOT/workspace"
rm -rf "$SMOKE_ROOT"
```

Unauthorized channel rejection smoke; this must return JSON on stderr with
`"status": "error"` and a `not authorized` message:

```bash
SMOKE_ROOT="$(mktemp -d /tmp/hermes-godmode-reject.XXXXXX)"
PYTHONPATH=src python3 -m hasystem.commands.gateway_adapter \
  --config examples/hermes-router.json \
  --event-json "$(cat examples/hermes-godmode-unauthorized-smoke.discord-event.json)" \
  --state-db "$SMOKE_ROOT/state.db" \
  --workspace "$SMOKE_ROOT/workspace"
rm -rf "$SMOKE_ROOT"
```

Operational runbook for enabling real iterations:

1. Confirm the gateway has been restarted after deploying the router config and
   wrapper path changes.
2. Run `godmode status` from the production Discord thread and trusted sender;
   verify `status: godmode_status`, `godmode.status: stopped`, and
   `godmode.iterations: 0`.
3. Run the unauthorized rejection smoke from a non-authorized thread/channel and
   verify it fails closed.
4. Change only one guardrail at a time. For the first real iteration set
   `max_iterations: 1`; keep `max_failures: 1`, `max_runtime_seconds` small,
   and `create_issue_when_empty: false` unless you explicitly want seed issue
   creation.
5. Monitor the returned GODMODE evidence for selected issue number, worker
   launch state, loop id, and stop reason. Use `godmode pause` or `godmode stop`
   before increasing iteration limits.
6. Roll back by restoring `max_iterations: 0` and restarting at the gateway
   runtime boundary.


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
