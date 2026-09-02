import hashlib
import os

from dotenv import load_dotenv

load_dotenv()  # must run BEFORE importing classify, which reads env vars at import time

from classify import classify_failure
from swytchcode_client import comment_on_issue, file_issue, get_run_logs, list_runs

OWNER = os.environ.get("GITHUB_OWNER")
REPO = os.environ.get("GITHUB_REPO")


def main():
    if not OWNER or not REPO:
        raise SystemExit("Set GITHUB_OWNER and GITHUB_REPO in .env first.")

    print(f"Checking {OWNER}/{REPO} for failed runs...")
    failed_runs = list_runs(OWNER, REPO)

    if not failed_runs:
        print("No failed runs found. Nothing to triage.")
        return

    for run in failed_runs:
        run_id = run["id"]
        name = run.get("name", "unnamed workflow")
        print(f"\nTriaging run #{run_id} ({name})...")

        log_text = get_run_logs(OWNER, REPO, run_id)
        if not log_text:
            print("  (no text logs found in this run's zip, skipping)")
            continue
        analysis = classify_failure(log_text)
        print("Classification:", analysis["classification"])

        # Deterministic idempotency key: same run + same commit never files
        # twice, even if this script runs again on retry or re-trigger.
        idempotency_key = hashlib.sha256(
            f"{run_id}-{run.get('head_sha', '')}".encode()
        ).hexdigest()

        issue = file_issue(
            OWNER,
            REPO,
            title=f"[{analysis['classification']}] CI failure in {name} (run #{run_id})",
            body=(
                f"**Root cause:** {analysis['explanation']}\n\n"
                f"**Suggested fix:** {analysis['suggested_fix']}\n\n"
                f"{run.get('html_url', '')}"
            ),
            labels=["ci-triage", analysis["classification"].lower()],
            idempotency_key=idempotency_key,
        )

        print("Filed issue:", issue.get("html_url", issue))

        for pr in run.get("pull_requests", []):
            comment_on_issue(
                OWNER,
                REPO,
                pr["number"],
                "🤖 PatchPilot triaged this failure — see the linked issue for the analysis.",
            )


if __name__ == "__main__":
    main()