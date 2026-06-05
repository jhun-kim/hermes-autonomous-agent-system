# Hermes live context-compression hook

This hook connects Hermes Agent's live context-compression lifecycle to the
`hasystem` `context.compaction` dispatch seam.

## Installed Hermes hook point

Hermes loads user gateway hooks from `~/.hermes/hooks/<hook>/HOOK.yaml` on
`gateway:startup`. This hook uses that startup event to wrap
`agent.conversation_compression.compress_context`. The wrapper observes a real
old-session → new-session rotation after Hermes compression succeeds, then sends
that lifecycle payload to `hasystem.commands.context_compression_hook`.

The local live gateway also needs to expose full `SessionSource` metadata on the
cached `AIAgent` object before every turn:

```python
setattr(agent, "_hasystem_gateway_source", source.to_dict())
```

That gives the hook Discord guild/channel/thread metadata while keeping the
compression wrapper itself outside Hermes core.

## Installation

From this repository:

```bash
mkdir -p ~/.hermes/hooks/hasystem-context-compaction-dispatch
cp integrations/hermes_hooks/context_compaction_dispatch/HOOK.yaml \
  ~/.hermes/hooks/hasystem-context-compaction-dispatch/HOOK.yaml
cp integrations/hermes_hooks/context_compaction_dispatch/handler.py \
  ~/.hermes/hooks/hasystem-context-compaction-dispatch/handler.py
```

Restart the gateway after installing:

```bash
hermes gateway restart
```

## Enablement

Default behavior is safe no-op. The hook does not dispatch unless explicitly
enabled:

```bash
export HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED=true
```

For repository-local smoke tests, point Hermes at this checkout and capture hook
evidence:

```bash
export PYTHONPATH="$PWD/src:$PYTHONPATH"
export HERMES_CONTEXT_COMPACTION_HOOK_LOG=/tmp/hasystem-context-compaction-hook.jsonl
export HERMES_CONTEXT_COMPACTION_HOOK_COMMAND='python -m hasystem.commands.context_compression_hook --state-db /tmp/hasystem-live-compaction.db --workspace /tmp/hasystem-live-compaction-workspace --compaction-rollover-threshold 1'
```

Optional metadata env vars used by the hook:

```bash
export HASYSTEM_REPO_HINT=jhun-kim/hermes-autonomous-agent-system
export HASYSTEM_ACTIVE_ISSUE_NUMBER=28
export HASYSTEM_ACTIVE_ISSUE_TITLE='Wire merged compaction hook into live Hermes gateway and run real Discord smoke'
export HASYSTEM_ACTIVE_ISSUE_LABELS='ai:in-progress,executor:lazycodex,priority:p3'
```

## Verification shape

A successful live lifecycle smoke writes a JSONL record whose inner command
stdout contains:

```json
{
  "status": "rollover_required",
  "dispatch": {"dispatched": true},
  "event": {"type": "context.compaction"},
  "continuation": {"conversation_id": "discord:<thread-or-channel>"}
}
```
