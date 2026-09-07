# PatchPilot 🚀

An AI agent that watches a GitHub repository for failed CI runs, diagnoses *why* each one failed using an LLM, and automatically files a labeled, already-explained GitHub issue — so no failing build gets silently ignored or re-run without anyone knowing why it broke.

Built using the [Swytchcode](https://www.swytchcode.com) CLI for reliable, policy-controlled, idempotent execution of real GitHub API calls.

---

## The problem

CI failures are usually either ignored or blindly re-run rather than actually read. Nobody wants to dig through a 400-line log at 6pm. That means:

- Real bugs slip through disguised as "just re-run it"
- Flaky tests quietly erode trust in the pipeline
- The same class of failure gets manually diagnosed over and over by different people

**PatchPilot turns a red ❌ into an already-triaged, already-explained GitHub issue the moment it happens** — no failure goes uninvestigated, and no one has to manually read the same stack trace twice.

---

## What it does

1. **Detects** — checks a GitHub repo for recent failed Actions runs
2. **Investigates** — downloads and unzips the failing run's logs
3. **Diagnoses** — sends the logs to an LLM (Groq, `openai/gpt-oss-120b`), which classifies the failure as:
   - `FLAKY_TEST` — a test that failed for a non-deterministic reason
   - `REAL_BUG` — an actual code defect
   - `ENV_CONFIG` — an environment, dependency, or configuration issue
   
   ...and drafts a root-cause explanation plus a suggested fix
4. **Acts** — files a GitHub issue with that full analysis, and comments on any pull request that triggered the run
5. **Stays idempotent** — checks for an existing issue on that exact run before creating a new one, so re-running PatchPilot (or a re-triggered CI run) never spams duplicate issues

---

## How it works (architecture)

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│  GitHub Actions  │────▶│    PatchPilot     │────▶│   GitHub Issues   │
│  (failed runs)   │     │  (Python agent)   │     │  (filed analysis) │
└─────────────────┘     └──────────────────┘     └───────────────────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │  Groq LLM API  │
                         │ (classification)│
                         └───────────────┘

All GitHub reads/writes go through the Swytchcode CLI, which handles:
  - OAuth authentication (no manual token wiring)
  - Idempotency checks before writes
  - Policy-restricted execution (agent can never merge/delete/force-push)
```

**Flow per run:**
```
list_runs() ──▶ find_existing_issue() ──▶ [exists?] ──yes──▶ skip
                                              │
                                              no
                                              ▼
                                     get_run_logs() ──▶ classify_failure() ──▶ file_issue() ──▶ comment_on_issue()
```

---

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| GitHub execution | [Swytchcode CLI](https://docs.swytchcode.com) (`github.action.runs.get`, `github.action.logs.get2`, `github.issue.create`, `github.issue.list`, `github.issue.comments.create`) |
| LLM reasoning | Groq API (`openai/gpt-oss-120b`) |
| Auth | Swytchcode's built-in OAuth2 provider connection (`swytchcode auth connect github`) |

---

## Project structure

```
patch-pilot/
├── main.py                # Orchestrates the detect → diagnose → act loop
├── classify.py             # Calls Groq to classify a failure from raw logs
├── swytchcode_client.py    # Wraps all Swytchcode CLI exec calls
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup

**Prerequisites:** Swytchcode CLI installed, initialized (`swytchcode init`), GitHub bundle fetched (`swytchcode get github`), and GitHub connected (`swytchcode auth connect github`).

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in GROQ_API_KEY, GITHUB_OWNER, GITHUB_REPO in .env
python main.py
```

Get a free Groq API key at [console.groq.com](https://console.groq.com) → API Keys.

---

## Production-readiness features

This wasn't built as a toy demo — it deliberately implements the two things that make "AI agent calls real APIs" actually safe to run unattended:

### Idempotency
GitHub's issue-creation API has no built-in idempotency key. Real idempotency here means: every issue PatchPilot files gets tagged with a deterministic label (`ci-run-{run_id}`). Before creating a new issue, PatchPilot searches for that label first — if one exists, it skips instead of duplicating. This means running PatchPilot on a cron, or re-triggering a failed workflow, never results in issue spam.

### Policy control
`swytchcode` evaluates guard policies (stored in `.swytchcode/integrations/policies.json`) before every execution. This agent is configured with 5 explicit blocks on destructive actions it should never be able to take, even if a bug, bad LLM output, or future code change tried to call them:

| Policy | Blocks |
|---|---|
| Block repo deletion | `github.repo.delete`, `github.repo.delete1` |
| Block merges | `github.merge.create`, `github.pull.merge.update`, `github.pull.updateBranch.update` |
| Block ref force-updates and deletes | `github.git.refs.update`, `github.git.refs.delete` |
| Block branch protection changes | `github.branche.protection.update`, `github.branche.protection.delete` |
| Block repo settings changes | `github.repo.update`, `github.repo.update1` |

Verified working — attempting a blocked action returns `POLICY_BLOCKED` before any API call is made:
```powershell
swytchcode exec github.repo.delete --input owner=... --input repo=... --dry-run
# → blocked by policy, no HTTP call made
```

Validate the policy set anytime with `swytchcode policy validate`.

---

## Example output

```
Checking myuser/myrepo for failed runs...

Triaging run #34098639400 (CI)...
Classification: ENV_CONFIG
Filed issue: https://github.com/myuser/myrepo/issues/1
```

---

## Why this is useful (real-world case)

- **For solo developers / small teams**: acts as an always-on first-pass triage engineer, so CI noise doesn't get ignored
- **For larger teams**: reduces the "who's going to look at this failing build" bystander effect — every failure gets an owner-ready starting point
- **As a demonstration**: shows a complete, production-minded agent pattern — detection, reasoning, guarded action, and idempotent execution — that generalizes to any "watch an event → reason about it → take a real action" agent, not just CI triage

---

## Known limitations / next steps

- Currently polls on-demand (`python main.py`) rather than reacting to a live webhook — a scheduled run (cron / GitHub Action) or a webhook listener would make it fully autonomous
- Classification quality depends on the LLM and log length (logs are truncated to ~8000 characters per call)
- Slack escalation for severity-based routing is scoped but not yet wired in — see `SLACK_CHANNEL_ID` in `.env.example` for the planned extension point