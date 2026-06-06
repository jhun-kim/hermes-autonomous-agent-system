# Hermes Autonomous Agent System

[![CI](https://github.com/jhun-kim/hermes-autonomous-agent-system/actions/workflows/ci.yml/badge.svg)](https://github.com/jhun-kim/hermes-autonomous-agent-system/actions/workflows/ci.yml)

Markdown harness engineering for a macOS cmux multi-agent workspace. The repository's center is one Discord thread mapped to one cmux workspace, with visible Codex/OmX/OmO worker surfaces operating GitHub issues from Markdown harnesses. Python remains the lightweight glue that validates those files and transports them into Hermes/GitHub/Discord/cmux execution.

The canonical thread workspace is documented in [`docs/THREAD_CMUX_WORKSPACE.md`](docs/THREAD_CMUX_WORKSPACE.md):

```text
Guild ID: 1478650515888934932
Parent Channel ID: 1478650642854580434
Thread ID: 1512679333611700224
```

The core promise is: **users operate multi-agent coding by editing Markdown and watching cmux surfaces, not by editing Python.** Start with [`docs/THREAD_CMUX_WORKSPACE.md`](docs/THREAD_CMUX_WORKSPACE.md), then run [`harnesses/issue-loop.md`](harnesses/issue-loop.md) and adjust the policies in [`policies/`](policies/) plus reusable prompts in [`templates/`](templates/).

Markdown harness map:

- [`docs/THREAD_CMUX_WORKSPACE.md`](docs/THREAD_CMUX_WORKSPACE.md) — central macOS cmux multi-agent workspace report for Discord thread `1512679333611700224`.
- [`harnesses/issue-loop.md`](harnesses/issue-loop.md) — one bounded issue from selection through PR handoff and follow-up issue creation.
- [`policies/issue-first.md`](policies/issue-first.md) — every repo-changing task starts with a confirmed GitHub issue.
- [`policies/cmux-first.md`](policies/cmux-first.md) — one Discord thread maps to one cmux workspace with visible worker surfaces.
- [`policies/evidence-and-no-fabrication.md`](policies/evidence-and-no-fabrication.md) — reports must be grounded in real command/GitHub evidence.
- [`templates/worker-prompt.md`](templates/worker-prompt.md), [`templates/follow-up-issue.md`](templates/follow-up-issue.md), and [`templates/verification-report.md`](templates/verification-report.md) — copy/paste contracts for workers and operators.
- [`docs/PLATFORM_SETUP.md`](docs/PLATFORM_SETUP.md) — macOS uses cmux by default and should install it when missing; Windows uses visible terminal Codex fallback instead of requiring cmux.

Validate the Markdown harness layer with:

```bash
python3 scripts/validate-harnesses
```

Current execution scope:

1. Parse GitHub repos as `owner/repo` or `https://github.com/owner/repo(.git)`.
2. Clone or update repos under `/Users/chai/Documents/GitHub` by default.
3. Ensure automation labels: `ai:ready`, `executor:lazycodex`, `priority:p2`, `ai:in-progress`, `ai:blocked`, `ai:done`.
4. Create `ai:ready` issues from Discord/Hermes task text.
5. Accept a raw Discord/Gateway message, JSON payload, or natural-language request with repo aliases/default repo context and orchestrate intake + run-loop with one command.
6. Select eligible `ai:ready` issues, store the active loop in SQLite, and prepare a worker command for a cmux-managed workspace/surface in the target repo.
7. Finalize by planning or running branch push, PR creation, issue comment, and label transition.

External commands go through a subprocess runner abstraction so tests can fake `git`, `gh`, `codex`, and `cmux`.

## 한국어 초보자 설치 / Korean beginner install

코딩을 전혀 모르는 사용자는 여기서 시작하세요:

1. GitHub에서 이 저장소를 다운로드하거나 clone 합니다.
2. LLM/에이전트에게 아래 프롬프트를 그대로 붙여넣습니다.
3. LLM이 터미널을 열고 OS/Python/Git 상태를 확인한 뒤, 한국어 설치 선택지를 보여주게 합니다.
4. 처음에는 반드시 `--dry-run`으로 명령 목록만 확인합니다.

LLM에게 붙여넣는 설치 시작 프롬프트:

```text
나는 코딩을 잘 모르는 일반 사용자입니다.
GitHub 저장소 jhun-kim/hermes-autonomous-agent-system 을 내 컴퓨터에 설치하고 싶습니다.

내 컴퓨터의 터미널을 열어 설치를 도와주세요.
먼저 운영체제, Python 3.10 이상 여부, Git 설치 여부를 확인하고,
위험한 명령은 실행 전에 한국어로 설명하고 확인을 받아주세요.
저장소 폴더에서 다음 명령으로 한국어 설치 선택지를 보여주세요.

python3 -m hasystem.commands.install_ko --dry-run

처음에는 live 실행을 하지 말고 dry-run/help 확인만 진행해주세요.
```

저장소 폴더에서 직접 실행할 수도 있습니다. `python3 --version`이 3.10보다 낮으면
`python3.11` 또는 `python3.10`으로 바꿔 실행하세요:

```bash
python3 -m hasystem.commands.install_ko --dry-run
python3 -m hasystem.commands.install_ko --choice 1 --dry-run  # 일반 사용자 설치 계획
python3 -m hasystem.commands.install_ko --choice 2 --dry-run  # 개발자 설치 계획
python3 -m hasystem.commands.install_ko --choice 3 --dry-run  # Gateway dry-run 점검
```

자세한 한국어 안내는 [`docs/INSTALL_KO.md`](docs/INSTALL_KO.md)를 보세요.
패키지 설치 후에는 `hasystem-install-ko --dry-run` 콘솔 명령도 사용할 수 있습니다.

## Worker surfaces: cmux first

Repository coding work is orchestrated through [cmux](https://github.com/manaflow-ai/cmux) workspace and surface primitives when cmux is installed:

- If the runtime is already inside cmux, `CMUX_WORKSPACE_ID` is the default target. The launcher creates an additional terminal surface in that caller workspace and sends the worker command there.
- For Discord-originated work, the Discord thread is the workspace boundary. The launcher derives a deterministic workspace name from `thread_name`/`thread_id` (falling back to channel context), reuses that workspace when present, creates it when absent, and provisions ten additive terminal surfaces by default for parallel Codex workers.
- Each default surface runs Codex CLI with a prompt that explicitly requires OmX/OmO skills/workflows, especially ULW for implementation work. OmX and OmO can still be selected as direct worker engines by labels, but Codex-in-cmux is the default surface shape.
- Parallel decomposition should increase surfaces inside the same Discord-thread workspace: Codex, OmX, and OmO workers can run side by side as separate cmux surfaces for the same thread.
- Branch isolation is mandatory for parallel surfaces. Use per-surface git worktrees and branches such as `ai/issue-51-topic/surface-01` through `surface-10`, then merge/combine verified branches into an integration branch before pushing and opening PR work.
- If no Discord context or caller workspace is available, the launcher creates one cmux workspace rooted at the target repository with `cmux new-workspace --cwd <repo> --command <worker> --focus false`.
- Worker launches are additive and focus-neutral. Do not select other workspaces, focus panes, open unbounded Terminal.app windows, or create unrelated cmux workspaces for parallel coding work.
- `executor:lazycodex`/`executor:codex`, `executor:omx`, and `executor:omo` select the worker engine/prompt shape. They do not select the terminal/session manager; cmux owns that layer by default.
- Operators can override the worker terminal/session manager with `HASYSTEM_WORKER_TERMINAL`:
  - `auto` or unset: use cmux when installed; otherwise use the direct/headless runner fallback.
  - `cmux`: require cmux and fail closed if the `cmux` binary is unavailable.
  - `terminal`/`Terminal.app`/`osascript`: launch workers in macOS Terminal.app even when cmux is installed.
  - `direct`/`headless`: run the worker command directly through the command runner without cmux or Terminal.app.
- Headless CI/tests can set `HASYSTEM_WORKER_TERMINAL=direct`, disable cmux preference, or run dry-run mode to avoid live cmux socket access.

## Operating rule: issue first, code second

When continuing this repo to the next stage, register the intended work as a GitHub issue first, then immediately read/confirm that issue before editing code. The confirmed issue number, title, body, and labels become the source of truth for the work bundle. Only after that confirmation should an agent modify code, docs, tests, branches, or PRs.

This rule is also recorded in `AGENTS.md` so future coding agents see it before making changes.

## Continuous integration

GitHub Actions runs the pytest suite on pushes to `main` and on pull requests using Python 3.11. The CI command is the same local verification command used below: `python3 -m pytest -q`.

## Quick start

For Korean beginner installation help, start with:

```bash
python3 -m hasystem.commands.install_ko --dry-run
```

For developer verification:

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

#### Context compression and Discord thread rollover

The old hasystem context-compression rollover integration has been removed.
Hermes may still compress its own conversation context normally, but this
repository no longer installs a hook, counts compactions, or creates Discord
continuation threads after seven compressions. Stale deployments that still call
`hasystem.commands.context_compression_hook` receive an inert `noop` response.

#### Real gateway deployment checklist

Use this checklist before pointing a production Hermes Discord gateway at
`scripts/hermes-gateway-wrapper` or an adapted copy:

1. Copy the wrapper beside the gateway runtime, or keep this repository checkout
   as a read-only deployment dependency, and set the wrapper's `--config` path to
   the deployed router JSON location rather than a developer-local path.
2. Validate channel/thread routing in dry-run mode with
   `examples/hermes-gateway-event.dry-run.json`; confirm the selected `repo`,
   `status`, and `hints` are what the gateway should report to Discord.
3. Optional automatic Discord intake uses the Hermes plugin extension point,
   not a core gateway fork: install
   `integrations/hermes_plugins/hasystem_gateway_intake/` as the user plugin
   directory `~/.hermes/plugins/hasystem-gateway-intake/`, add
   `hasystem-gateway-intake` to `plugins.enabled`, and restart the gateway.
   Hermes invokes the plugin via `pre_gateway_dispatch` before auth/pairing and
   ordinary agent dispatch. For configured parent channels, ordinary human
   Discord thread messages route to hasystem by default. Users only need an
   explicit prefix for controls or escape hatches:
   - exact `godmode`, `godmode status`, `godmode pause`, `godmode resume`, or
     `godmode stop` controls;
   - `/hasystem ...`, `!hasystem ...`, `@hasystem ...`, or `hasystem ...`;
   - `/hermes ...` or `@hermes ...` to bypass hasystem and let normal Hermes
     dispatch handle the message.

   Configure the live adapter command in the gateway environment or launchd
   service. Auto-routing is fail-closed: it only applies when the source
   channel/thread matches `HASYSTEM_GATEWAY_PARENT_CHANNEL_IDS`; if that env var
   is unset, the plugin reads the deployed router JSON from
   `HERMES_GATEWAY_ROUTER_CONFIG` or
   `~/.hermes/hasystem-gateway-runtime/hermes-router.json` and uses its
   `channel_default_repos`/`godmode.authorized_channel_ids` entries.

   ```bash
   export HASYSTEM_GATEWAY_ADAPTER_COMMAND="$HOME/.hermes/hasystem-gateway-runtime/hasystem-gateway-wrapper --live"
   export HASYSTEM_GATEWAY_PARENT_CHANNEL_IDS="1478650642854580434"
   ```

   For a Discord thread message, the plugin builds the adapter envelope with
   `guild_id`, parent `channel_id`, `thread_id`/`thread_name`, sender metadata,
   message id, and routed content, then returns
   `{ "action": "skip" }` from `pre_gateway_dispatch` after scheduling the
   adapter response back to the same Discord thread. Keep `allow_repos` in the
   router JSON; the wrapper's live mode remains fail-closed.
4. Run the isolated live-mode fixture before enabling live Discord events:
   `python3 -m pytest -q tests/test_gateway_wrapper_live_fixture.py tests/test_hasystem_gateway_intake_plugin.py`.
5. Review the fail-closed repository boundary. Keep production repos in
   `allow_repos` or pass explicit `--allow-repo owner/repo` entries; do not use
   `--allow-any-repo` by default.
6. Restart only at runtime boundaries: use `/restart` or restart the gateway
   process after changing the installed wrapper/adapter, cmux worker-surface
   runtime, environment variables, router config file path, or installed plugin
   files. Ordinary new Discord requests in an already configured runtime do not
   require restart.
7. Keep a rollback note with the previous wrapper path, router config path,
   plugin enabled state, and adapter version so rollback is a config/path revert
   plus the same restart boundary from step 6.

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
