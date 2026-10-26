"""One resumable native image-to-multiview task; never submits a 3D model.

The file gate validates transport only. Identity and pose require a separate review.
"""
import argparse
import fcntl
import hashlib
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image
from tripo_run import api, write

HERE = Path(__file__).resolve().parent
VIEWS = ("front", "left", "back", "right")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def image_info(data):
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        return {"width": im.width, "height": im.height, "format": im.format}


def output_shape(value):
    """Describe an unexpected response without disclosing temporary URLs."""
    if isinstance(value, dict):
        return {k: output_shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return [output_shape(v) for v in value]
    return type(value).__name__


def run(cfg_path, dry_run=False):
    cfg = json.loads(cfg_path.read_text())
    if cfg["endpoint"] != "/generation/image-to-multiview" or cfg["parameters"]:
        raise RuntimeError("Only the documented input-only multiview request is supported")
    source = (HERE / cfg["source_file"]).resolve()
    review = json.loads((HERE / cfg["source_review"]).read_text())
    if review.get(cfg["source_approval_key"]) is not True:
        raise RuntimeError("Source pose-anchor review does not approve this operation")
    data = source.read_bytes()
    info = image_info(data)
    if info["format"] not in ("PNG", "JPEG", "WEBP"):
        raise RuntimeError("Unsupported source image format")
    public = {"endpoint": cfg["endpoint"], "source_file": cfg["source_file"],
              "source_sha256": sha(data), "source_image": info,
              "source_review_sha256": sha((HERE / cfg["source_review"]).read_bytes()),
              "parameters": {}, "expected_credits": cfg["expected_credits"]}
    fingerprint = sha(json.dumps(public, sort_keys=True).encode())
    if dry_run:
        print(json.dumps({**public, "network_requests": 0}, ensure_ascii=False, indent=2))
        return
    out = HERE / cfg["output"]
    out.mkdir(parents=True, exist_ok=True)
    with (out / ".run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = out / "state.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state and state["request_fingerprint"] != fingerprint:
            raise RuntimeError("Existing task belongs to a different input or review")
        if state.get("status") == "downloaded":
            for item in state["downloads"]:
                if sha((out / item["file"]).read_bytes()) != item["sha256"]:
                    raise RuntimeError("Downloaded artifact changed; no paid retry")
            print("Already downloaded and hashes verified; no network or paid submission")
            return
        if not state.get("task_id"):
            if state.get("submission_started"):
                raise RuntimeError("Prior POST outcome unknown; automatic resubmission refused")
            write(out / "request-public.json", public)
            (out / "executed-source.py").write_bytes(Path(__file__).read_bytes())
            (out / "executed-api-helper.py").write_bytes((HERE / "tripo_run.py").read_bytes())
            with source.open("rb") as f:
                token = api("POST", "/files", files={"file": (source.name, f, Image.MIME[info["format"]])})["file_token"]
            state = {"submission_started": True, "started_at": time.time(),
                     "request_fingerprint": fingerprint, "status": "submitting"}
            write(state_path, state)
            try:
                task = api("POST", cfg["endpoint"], json={"input": token})
                state["task_id"] = task["task_id"]
            except Exception as exc:
                state["submission_error_type"] = type(exc).__name__
                write(state_path, state)
                raise
            write(state_path, state)
            print("task_id", state["task_id"], flush=True)
        last = None
        for _ in range(90):
            task = api("GET", "/tasks/" + state["task_id"])
            status, progress = task.get("status"), task.get("progress")
            safe = {k: task.get(k) for k in ("task_id", "type", "status", "progress",
                                             "credits_consumed", "consumed_credit", "created_at", "completed_at", "error_code")}
            safe["output_shape"] = output_shape(task.get("output", {}))
            write(out / "task-status.json", safe)
            if (status, progress) != last:
                print(status, progress, flush=True)
                last = status, progress
            if status == "success":
                break
            if status in ("failed", "cancelled", "canceled", "banned", "expired"):
                state.update(status=status, credits_consumed=task.get("credits_consumed"))
                write(state_path, state)
                raise RuntimeError("Multiview task reached terminal failure; no paid retry")
            time.sleep(8)
        else:
            raise RuntimeError("Polling timeout; resume same task instead of submitting another")
        output = task.get("output", {})
        state.update(status="success_pending_download", credits_consumed=task.get("credits_consumed", task.get("consumed_credit")))
        write(state_path, state)
        # Observed V3 response nests the four fields; docs show them at top level.
        # Normalize transport only; preserve provider view labels without guessing.
        nested = output.get("generate_multiview_image")
        if isinstance(nested, dict):
            if any(view + "_view_url" in output for view in VIEWS):
                raise RuntimeError("Ambiguous direct and nested view payloads")
            output = nested
            state["output_container"] = "output.generate_multiview_image"
        else:
            state["output_container"] = "output"
        (out / "executed-download-source.py").write_bytes(Path(__file__).read_bytes())
        expected = {view: output.get(view + "_view_url") for view in VIEWS}
        if not all(isinstance(url, str) and url.startswith("https://") for url in expected.values()):
            raise RuntimeError("Output contract differs from documented four view URLs; inspect sanitized output_shape")
        downloads = []
        for view, url in expected.items():
            response = requests.get(url, timeout=120)
            if response.status_code != 200:
                raise RuntimeError("View download returned HTTP " + str(response.status_code))
            blob = response.content
            details = image_info(blob)
            suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(details["format"])
            if not suffix:
                raise RuntimeError("Unexpected output image format")
            dest = out / (view + suffix)
            dest.write_bytes(blob)
            downloads.append({"view": view, "file": dest.name, "sha256": sha(blob), "bytes": len(blob), **details})
            print("Downloaded", view, details["width"], details["height"], flush=True)
        checks = {"all_four_images_decoded": len(downloads) == 4,
                  "minimum_256px_pass": all(min(x["width"], x["height"]) >= 256 for x in downloads),
                  "independent_image_hashes": len({x["sha256"] for x in downloads}) == 4,
                  "identity_pose_and_view_labels_reviewed": False,
                  "approved_for_3d_submission": False}
        write(out / "file-check.json", checks)
        state.update(status="downloaded", downloads=downloads,
                     elapsed_seconds=round(time.time() - state["started_at"], 2),
                     approved_for_3d_submission=False)
        if task.get("created_at") and task.get("completed_at"):
            state["server_task_seconds"] = round((datetime.fromisoformat(task["completed_at"]) - datetime.fromisoformat(task["created_at"])).total_seconds(), 3)
        state["elapsed_seconds_scope"] = "Submission through download; includes polling and response-adapter interruption"
        write(state_path, state)
        print(json.dumps({"status": state["status"], "elapsed_seconds": state["elapsed_seconds"],
                          "credits_consumed": state["credits_consumed"], "file_checks": checks}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        run(args.config, args.dry_run)
    except Exception as exc:
        # API errors may include signed download URLs; do not print their message.
        print("Multiview stopped:", type(exc).__name__, "Inspect saved sanitized state; do not resubmit blindly.", flush=True)
        sys.exit(1)
