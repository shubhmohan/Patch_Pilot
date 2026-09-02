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
    return result.get("workflow_runs") or result.get("data") or result


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


def file_issue(owner: str, repo: str, title: str, body: str, labels: list, idempotency_key: str) -> dict:
    return swytchcode_exec(
        "github.issue.create",
        inputs={"owner": owner, "repo": repo},
        body={
            "title": title,
            "body": body,
            "labels": labels,
            "idempotency_key": idempotency_key,
        },
    )


def comment_on_issue(owner: str, repo: str, issue_number: int, body: str) -> dict:
    return swytchcode_exec(
        "github.issue.comments.create",
        inputs={"owner": owner, "repo": repo, "issue_number": issue_number},
        body={"body": body},
    )