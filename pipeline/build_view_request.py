"""Build reference requests from shared view rules and per-cat evidence; no network.

This does not automate photo role assignment, generation execution or visual QA.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMON = """Use case: identity-preserve. Asset: one full-body cardinal-view modeling reference of the same personalized cat.
Primary request: rotate ONLY the camera to the requested view of the supplied complete neutral standing cat, retaining its proportions, standing pose and raised open tail curve. Use the real photographs to preserve this individual cat's asymmetric markings. Photographs outrank generated references whenever markings conflict. Do not infer the opposite cheek by mirroring.
Pose: four anatomical legs, relaxed weight-bearing stance, level back, head/neck/muzzle aligned forward with the spine, all paws on one level ground plane. Camera rotation must not change limb positions, body length/width, head size or tail curve. Natural overlapping silhouettes in a cardinal view are allowed; never create extra legs for visibility. Include full ears, every visible paw and tail tip with generous margins.
Style: match the art reference's clean low-poly volume and natural adult feline facial structure. Medium coherent body planes, finer necessary eyelid/muzzle/paw planes, broad readable coat patches with restrained color variation. Solid matte surfaces and clean outlines; no fur strands, whiskers, spikes, wireframe, fake triangle outlines or dense decorative triangle noise. Do not shrink this into a toy or enlarge the head/eyes.
Presentation: one cat, one view, square image, plain pale gray background, neutral even illumination, minimal cast shadow. Orthographic camera, no perspective glamour angle. No text, labels, panel collage, UI, props, border or watermark. This is an AI 2D modeling reference, not an image of the original lying pose.
"""


def build(profile_path, view):
    profile = json.loads(profile_path.read_text())
    spec = profile["views"][view]
    sources = []
    for name in spec["inputs"]:
        source = profile["sources"][name]
        path = (HERE / source["path"]).resolve()
        if not path.is_file():
            raise ValueError("Required checked reference is missing: " + source["path"])
        sources.append({"id": name, **source, "absolute_path": str(path),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    evidence = json.loads((HERE / profile["identity_features"]).read_text())
    identity = "\n".join(f'- {f["region"]}: {f["description"]} [evidence={f["evidence"]}]'
                         for f in evidence["features"])
    roles = "\n".join(f'Image {i+1}: {s["role"]}.' for i, s in enumerate(sources))
    prompt = COMMON + "\nINPUT ROLES\n" + roles + "\nREQUESTED CAMERA\n" + spec["camera"] + "\nPER-CAT IDENTITY EVIDENCE\n" + identity
    out = HERE / profile["output"]
    out.mkdir(parents=True, exist_ok=True)
    request = {"provider": "built_in_imagegen", "model": None, "seed": None,
               "view": view, "inputs": sources, "prompt": prompt,
               "status": "prepared_not_executed", "artifact_kind": "AI_2D_not_mesh"}
    request_file = out / (view + "-request.json")
    if request_file.exists():
        raise ValueError("Request already exists; do not overwrite execution evidence")
    request_file.write_text(json.dumps(request, ensure_ascii=False, indent=2))
    (out / (view + "-prompt.txt")).write_text(prompt)
    (out / "executed-request-builder.py").write_bytes(Path(__file__).read_bytes())
    print(json.dumps({"view": view, "request": str(request_file), "input_count": len(sources), "network_requests": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("profile", type=Path)
    parser.add_argument("view", choices=("front", "left", "back", "right"))
    args = parser.parse_args()
    build(args.profile, args.view)
