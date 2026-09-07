"""Thin wrapper around the Swytchcode CLI's `exec` command.

Confirmed from `swytchcode exec --help`:
    swytchcode exec <canonical_id> --input k=v --param k=v --body '<json>' --json

- --input   : path/template parameters (e.g. owner, repo, run_id) — repeatable
- --param   : query-string parameters (e.g. status=failure) — repeatable
- --body    : JSON request body, as a file path or inline JSON string
- --json    : print the response as JSON to stdout (what we parse)
- --explain : print what WOULD be called, with no live API call — great for
              verifying an action name/param mapping before spending a real call
"""

import json
import subprocess
import tempfile
import zipfile
import os


def swytchcode_exec(action: str, inputs: dict | None = None, params: dict | None = None,
                     body: dict | None = None, explain: bool = False,
                     output_file: str | None = None) -> dict:
    cmd = ["swytchcode", "exec", action]
    for k, v in (inputs or {}).items():
        cmd += ["--input", f"{k}={v}"]
    for k, v in (params or {}).items():
        cmd += ["--param", f"{k}={v}"]
    if body is not None:
        cmd += ["--body", json.dumps(body)]
    if explain:
        cmd.append("--explain")
    elif output_file:
        cmd += ["--output", output_file]
    else:
        cmd.append("--json")

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"swytchcode exec {action} failed:\n{result.stderr}")
    if explain:
        print(result.stdout)  # --explain prints a plan, not JSON — just show it
        return {}
    if output_file:
        return {}  # binary response was written straight to output_file
    return json.loads(result.stdout) if result.stdout.strip() else {}


def list_runs(owner: str, repo: str, explain: bool = False):
    """List failed workflow runs for a repo.

    TODO verify: 'github.action.runs.get' is our best guess from `swytchcode
    list` output. Before running for real, sanity-check with:
        list_runs(owner, repo, explain=True)
    which uses --explain to show the planned call without hitting the API.
    If the shape looks wrong, try github.action.runs.get1 / get2 instead.
    """
    result = swytchcode_exec(
        "github.action.runs.get",
        inputs={"owner": owner, "repo": repo},
        params={"status": "failure"},
        explain=explain,
    )
    if explain:
        return []
    # Confirmed shape: {"data": {"total_count": N, "workflow_runs": [...]}, "request": {...}, "status_code": 200}
    return result.get("data", {}).get("workflow_runs", [])


def get_run_logs(owner: str, repo: str, run_id: int) -> str:
    """Fetch and concatenate all log text for a specific workflow run.

    Confirmed action: 'github.action.logs.get2' -> GET .../actions/runs/{run_id}/logs
    This endpoint returns a ZIP of per-job log files, not JSON, so we write
    it to a temp file with --output, then unzip and concatenate the text.
    """
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "logs.zip")
        swytchcode_exec(
            "github.action.logs.get2",
            inputs={"owner": owner, "repo": repo, "run_id": run_id},
            output_file=zip_path,
        )

        combined = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name.endswith(".txt"):
                    with zf.open(name) as f:
                        combined.append(f"--- {name} ---\n{f.read().decode('utf-8', errors='replace')}")
        return "\n\n".join(combined)


def find_existing_issue(owner: str, repo: str, run_id: int):
    """Check whether an issue for this exact CI run has already been filed.

    This IS the idempotency mechanism. GitHub's issue-creation endpoint has
    no built-in idempotency key — passing one (as the old code did) is
    silently ignored. Real idempotency here means: tag every issue PatchPilot
    creates with a run-specific label (ci-run-{run_id}), then search for that
    label before creating a new one. A re-run or re-trigger of the same
    workflow run will find the existing issue and skip instead of duplicating.

    TODO verify: 'github.issue.list' is our best guess from `swytchcode
    list`. Sanity-check the mapping first with:
        swytchcode exec github.issue.list --input owner=X --input repo=Y --param labels=ci-run-123 --param state=all --explain
    """
    result = swytchcode_exec(
        "github.issue.list",
        inputs={"owner": owner, "repo": repo},
        params={"labels": f"ci-run-{run_id}", "state": "all"},
    )
    issues = result.get("data", result)
    if isinstance(issues, dict):
        issues = issues.get("issues") or issues.get("items") or []
    return issues[0] if issues else None


def file_issue(owner: str, repo: str, title: str, body: str, labels: list, run_id: int) -> dict:
    result = swytchcode_exec(
        "github.issue.create",
        inputs={"owner": owner, "repo": repo},
        body={
            "title": title,
            "body": body,
            # The run-specific label is what find_existing_issue() searches
            # on — this is what actually makes filing idempotent per run.
            "labels": labels + [f"ci-run-{run_id}"],
        },
    )
    # Same wrapper shape as list_runs: {"data": {...actual issue...}, "request": ..., "status_code": ...}
    return result.get("data", result)


def comment_on_issue(owner: str, repo: str, issue_number: int, body: str) -> dict:
    result = swytchcode_exec(
        "github.issue.comments.create",
        inputs={"owner": owner, "repo": repo, "issue_number": issue_number},
        body={"body": body},
    )
    return result.get("data", result)