# Basic Markdown Harness Run

This example shows the minimum operator-facing flow.

1. Edit `harnesses/issue-loop.md` to adjust the workflow.
2. Edit `policies/issue-first.md` or `policies/cmux-first.md` to adjust rules.
3. Run:

```bash
python3 scripts/validate-harnesses
```

4. Give the harness to Hermes/Codex as the work contract.
5. Verify that the final report includes real issue, PR, commit, and command evidence.
