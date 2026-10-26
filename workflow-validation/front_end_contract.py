"""Offline request preflight and sanitized local evidence. No network or secrets.

Run: python3 experiments/workflow-validation-v001/front_end_contract.py
Outputs are evidence of configuration checks, never of generation/visual quality.
"""
import copy
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
REFERENCE = PROJECT.parent / "catworld"
VIEWS = ("front", "left", "back", "right")
ALLOWED = {
    "model", "texture", "pbr", "texture_alignment", "texture_version",
    "texture_quality", "geometry_quality", "smart_low_poly", "face_limit",
    "quad", "auto_size", "generate_parts", "orientation", "export_uv",
    "model_seed", "texture_seed", "delight", "compress", "export_orientation",
}


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def image_size(path):
    """Header dimensions only; this is not image decoding or EXIF normalization."""
    with path.open("rb") as f:
        prefix = f.read(24)
        if prefix[:8] == b"\x89PNG\r\n\x1a\n":
            if len(prefix) != 24 or prefix[12:16] != b"IHDR":
                raise ValueError("invalid PNG header")
            return list(struct.unpack(">II", prefix[16:24]))
        f.seek(0)
        if f.read(2) != b"\xff\xd8":
            raise ValueError("header reader supports PNG/JPEG only")
        sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
               0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while True:
            b = f.read(1)
            if not b:
                raise ValueError("JPEG has no SOF dimensions")
            if b != b"\xff":
                continue
            b = f.read(1)
            while b == b"\xff":
                b = f.read(1)
            if not b:
                raise ValueError("truncated JPEG marker")
            marker = b[0]
            if marker in {0xDA, 0xD9}:
                raise ValueError("JPEG ended before SOF")
            if marker in {0x00, 0x01, *range(0xD0, 0xD9)}:
                continue
            raw = f.read(2)
            if len(raw) != 2:
                raise ValueError("truncated JPEG segment")
            n = struct.unpack(">H", raw)[0]
            if n < 2:
                raise ValueError("invalid JPEG segment")
            if marker in sof:
                data = f.read(5)
                if len(data) != 5:
                    raise ValueError("truncated JPEG SOF")
                height, width = struct.unpack(">HH", data[1:5])
                return [width, height]
            f.seek(n - 2, 1)


def glb_summary(path):
    with path.open("rb") as f:
        magic, version, length = struct.unpack("<4sII", f.read(12))
        if magic != b"glTF" or version != 2 or length != path.stat().st_size:
            raise ValueError("invalid GLB header/length")
        n, kind = struct.unpack("<II", f.read(8))
        if kind != 0x4E4F534A or n > length - 20:
            raise ValueError("invalid GLB JSON chunk")
        d = json.loads(f.read(n))
    triangles = 0
    for mesh in d.get("meshes", []):
        for primitive in mesh["primitives"]:
            if primitive.get("mode", 4) != 4:
                raise ValueError("non-triangle primitive needs separate counting")
            accessor = primitive.get("indices", primitive["attributes"]["POSITION"])
            count = d["accessors"][accessor]["count"]
            if count % 3:
                raise ValueError("triangle index count is not divisible by 3")
            triangles += count // 3
    return {"triangles": triangles, "meshes": len(d.get("meshes", [])),
            "animations": len(d.get("animations", [])),
            "sha256": sha256(path), "bytes": path.stat().st_size,
            "validation_scope": "container_and_counts_only_not_geometry_or_quality"}


def validate_parameters(p):
    unknown = set(p) - ALLOWED
    if unknown:
        raise ValueError(f"unsupported/legacy fields: {sorted(unknown)}")
    if p.get("model") != "v3.1-20260211":
        raise ValueError("this preflight is scoped to the pinned H3.1 profile")
    for k in ("texture", "pbr", "smart_low_poly", "quad", "auto_size",
              "generate_parts", "export_uv", "delight"):
        if k in p and type(p[k]) is not bool:
            raise ValueError(f"{k} must be boolean")
    for k in ("model_seed", "texture_seed", "face_limit"):
        if k in p and type(p[k]) is not int:
            raise ValueError(f"{k} must be integer")
    if not p.get("texture") or p.get("pbr") or p.get("quad") or p.get("generate_parts"):
        raise ValueError("this experiment requires textured triangle mesh without PBR/parts")
    if p.get("smart_low_poly") is not True or not 500 <= p.get("face_limit", 0) <= 20000:
        raise ValueError("smart-low-poly triangle limit must be in 500..20000")
    enums = {
        "texture_quality": {"standard", "detailed", "fast", "extreme"},
        "geometry_quality": {"standard", "detailed"},
        "texture_alignment": {"original_image", "geometry"},
        "orientation": {"default", "align_image"},
        "texture_version": {"v3.0-20250812", "v3.5-20260815"},
    }
    for k, values in enums.items():
        if p.get(k) not in values:
            raise ValueError(f"unsupported {k}")
    if ("delight" in p or p.get("texture_quality") == "fast") and p.get("texture_version") != "v3.5-20260815":
        raise ValueError("delight/fast require the v3.5 texture model")
    if "compress" in p or "export_orientation" in p:
        raise ValueError("compression/orientation export must remain unset during this POC")


def build_request(parameters, view_tokens):
    validate_parameters(parameters)
    if set(view_tokens) != set(VIEWS):
        raise ValueError("POC requires exactly four named views; API minimum is a separate rule")
    if any(not isinstance(v, str) or not v.strip() for v in view_tokens.values()):
        raise ValueError("view input must be nonempty")
    if len(set(view_tokens.values())) != 4:
        raise ValueError("duplicated view inputs would conceal missing viewpoints")
    return {"inputs": [{v: view_tokens[v]} for v in VIEWS], **copy.deepcopy(parameters)}


def main():
    profile = json.loads((HERE / "front-end-profile.json").read_text())
    params = profile["tripo"]["request_parameters"]
    previews = {}
    for name, overrides in {"baseline": {}, **profile["tripo"]["variants"]}.items():
        variant = {**params, **overrides}
        previews[name] = build_request(variant, {v: f"file_DRY_RUN_{v}" for v in VIEWS})
    records = []
    for p in sorted((REFERENCE / "gen_output/tripo").glob("*.json")):
        d = json.loads(p.read_text())
        # Whitelist numerical/config fields. Never copy signed output URLs or tokens.
        allowed = (ALLOWED - {"model"}) | {"model_version"}
        original = {k: v for k, v in d.get("input", {}).items() if k in allowed}
        glb = p.with_name(p.stem + "_model.glb")
        record = {"source": str(p), "source_sha256": sha256(p),
                  "type": d.get("type"), "status": d.get("status"),
                  "recorded_parameters": original,
                  "historical_credits": d.get("consumed_credit"),
                  "not_recorded": [k for k in ("model_seed", "texture_seed", "texture_version", "texture_quality") if k not in original]}
        if glb.exists():
            record["model"] = glb_summary(glb)
            if original.get("face_limit"):
                record["observed_face_limit_exceeded"] = record["model"]["triangles"] > original["face_limit"]
        records.append(record)
    photos = [{"photo_id": f"source_{i:02d}", "path": str(p.relative_to(PROJECT)),
               "sha256": sha256(p), "stored_pixel_size": image_size(p),
               "status": "inventoried_not_identity_or_quality_reviewed"}
              for i, p in enumerate(sorted((PROJECT / "example").glob("*.jpg")), 1)]
    views = [{"view": v, "path": str(REFERENCE / f"gen_input/{v}.png"),
              "stored_pixel_size": image_size(REFERENCE / f"gen_input/{v}.png"),
              "sha256": sha256(REFERENCE / f"gen_input/{v}.png"),
              "status": "existing_reference_not_approved_as_new_generation_input"} for v in VIEWS]
    report = {"scope": "offline_configuration_and_existing_artifact_inspection",
              "profile_sha256": sha256(HERE / "front-end-profile.json"),
              "reference_records": records, "source_photos": photos, "existing_views": views,
              "checks_passed": ["baseline_and_four_variants_constructed", "historical_glb_headers_and_counts_read"],
              "submission_ready": False, "generation_executed": False,
              "visual_quality_verified": False, "open_blockers": profile["qa"]["open_blockers"]}
    (HERE / "front-end-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (HERE / "tripo-requests.dry-run.json").write_text(json.dumps({"dry_run": True, "contains_placeholder_tokens": True, "requests": previews}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"photos_inventoried": len(photos), "historical_records": len(records),
                      "request_profiles_checked": len(previews), "submission_ready": False,
                      "open_blockers": len(report["open_blockers"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
