import os

from dotenv import load_dotenv

load_dotenv()  # must run BEFORE importing classify, which reads env vars at import time

from classify import classify_failure
from swytchcode_client import comment_on_issue, file_issue, find_existing_issue, get_run_logs, list_runs

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

        # Idempotency check: has PatchPilot already filed an issue for this
        # exact run? If so, skip instead of creating a duplicate. This is
        # what actually protects against re-runs/retries, not a fake key.
        existing = find_existing_issue(OWNER, REPO, run_id)
        if existing:
            print(f"  Already triaged — skipping. See {existing.get('html_url', existing)}")
            continue

        log_text = get_run_logs(OWNER, REPO, run_id)
        if not log_text:
            print("  (no text logs found in this run's zip, skipping)")
            continue
        analysis = classify_failure(log_text)
        print("Classification:", analysis["classification"])

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
            run_id=run_id,
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