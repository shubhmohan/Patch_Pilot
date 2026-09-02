# PatchPilot

An AI agent that watches a GitHub repo for failed CI runs, diagnoses *why* they failed using Claude, and automatically files a labeled, already-explained GitHub issue — instead of leaving the failure for someone to manually dig through logs for.

## What it does

1. Checks a repo for recent failed GitHub Actions runs
2. Pulls the failing run's logs
3. Sends the logs to Claude, which classifies the failure as `FLAKY_TEST`, `REAL_BUG`, or `ENV_CONFIG` and drafts a root-cause explanation + suggested fix
4. Files a GitHub issue with that analysis, and comments on any linked PR
5. Uses a deterministic idempotency key (hash of run ID + commit SHA) so retried/re-triggered runs never create duplicate issues

## Setup

Assumes you already have the Swytchcode CLI installed, initialized (`swytchcode init`), the GitHub bundle fetched (`swytchcode get github`), and GitHub connected (`swytchcode auth connect github`).

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# fill in ANTHROPIC_API_KEY, GITHUB_OWNER, GITHUB_REPO
python main.py
```

## Known TODOs before your first real run

**1. Confirm the CLI's parameter flag.** `swytchcode_client.py` calls `swytchcode exec <action> --json '<params>'` — this flag name is a best guess. Run `swytchcode exec --help` and confirm whether it's actually `--json`, `--data`, or something else, then fix the one line in `swytchcode_exec()`.

**2. Confirm the two ambiguous action names.** `list_runs` and `get_run_logs` use `github.action.runs.get` and `github.action.logs.get` — GitHub's bundle exposes overloaded, unlabeled variants (`get`, `get1`, `get2`) for what should be distinct "list" vs "get one" endpoints. If either throws a shape error, run:
```bash
swytchcode info github.action.runs.get1
swytchcode info github.action.logs.get1
```
and swap the action name in `swytchcode_client.py` — no other code changes needed.

## Production-readiness features

- **Idempotency**: retried runs update/skip instead of duplicating issues
- **Policy control** (recommended next step): scope `tooling.json` to allowlist only `github.issue.create` and `github.issue.comments.create` for this agent — it should never be able to merge, delete, or force-push anything
