# Platform Setup Guide

This is a user guide for choosing the workspace layer before running the Markdown harnesses.

## macOS: cmux by default

On macOS, use cmux as the default workspace/surface layer. A Discord thread should map to one cmux workspace, and Codex should run visibly inside cmux terminal surfaces.

### If cmux is already installed

```bash
cmux version
cmux /path/to/repo
```

Then give the agent the issue-loop harness:

```bash
python3 scripts/validate-harnesses
```

### If cmux is missing

Ask the LLM/operator to install cmux before starting repository work. A safe beginner prompt is:

```text
I am on macOS and this repository expects cmux as the default workspace layer.
Please check whether cmux is installed. If it is missing, install it using the official cmux installation path for my machine, then verify with `cmux version`.
Do not start GitHub issue work until cmux is installed or you have explained the blocker.
```

A command-oriented operator can begin with:

```bash
command -v cmux || echo "cmux is missing; install cmux before running the harness"
cmux version
```

If installation needs a package manager or downloaded installer, the LLM/operator must explain the command and ask before running privileged or system-changing commands.

## Windows: terminal Codex fallback

On Windows, do not require cmux. Use a normal terminal environment with Codex CLI as the visible worker surface.

Recommended terminal options:

- Windows Terminal with PowerShell
- Windows Terminal with WSL, if the repository workflow already uses WSL
- A Git Bash terminal when Git tooling is required

Minimum checks:

```powershell
codex --version
git --version
python --version
```

Run the Markdown harness workflow from the terminal and keep the Codex session visible to the user. The evidence rule still applies: do not claim Codex execution unless the terminal session, command invocation, or log is inspectable.

## Cross-platform rule

- macOS: prefer cmux; install or guide installation when missing.
- Windows: use terminal Codex fallback; do not block on cmux.
- Linux or unknown: prefer cmux when available, otherwise use a visible terminal Codex session and report the chosen fallback.
