"""Read saved actual-GLB review scenes; reframe only, with identical lighting.

The front/top bbox crop is a review-camera heuristic, not an anatomical mask
and is never used by the texture processing algorithm.
"""
import hashlib
import json
import math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
cases = {
    'baseline': BASE / '25-appearance-diagnostic/matte-candidate/preview',
    'delta18': HERE / 'results-v001/delta18/preview',
    'delta28': HERE / 'results-v001/delta28/preview',
}
out = HERE / 'detail-v001'
if out.exists():
    raise RuntimeError('Preserve previous detail renders')
out.mkdir()
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
records = []
expected = None
for label, folder in cases.items():
    report = json.loads((folder / 'report.json').read_text())
    source = Path(report['source'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == report['source_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(folder / 'scene.blend'))
    names = [g['name'] for g in report['geometry']]
    meshes = [bpy.data.objects[name] for name in names]
    pts = np.array([ob.matrix_world @ v.co for ob in meshes for v in ob.data.vertices])
    lo, hi = pts.min(0), pts.max(0)
    # This experiment's standardized cat points +X in its Blender review scene.
    # Only camera framing uses this orientation; no anatomical processing.
    keep = (pts[:, 0] >= lo[0] + .70 * (hi[0] - lo[0])) & (pts[:, 2] >= lo[2] + .50 * (hi[2] - lo[2]))
    if keep.sum() < 10:
        raise RuntimeError('Insufficient front/top geometry for review framing')
    q = pts[keep]
    center = Vector((q.min(0) + q.max(0)) / 2)
    span = float(np.linalg.norm(q.max(0) - q.min(0))) * 1.10
    framing = {'center': list(center), 'ortho_scale': span}
    if expected is None:
        expected = framing
    assert framing == expected, 'Candidate geometry/framing differs'
    sc = bpy.context.scene
    sc.cycles.samples = 48
    sc.cycles.seed = 0
    sc.render.resolution_x = 768
    sc.render.resolution_y = 768
    sc.render.resolution_percentage = 100
    cam = sc.camera
    cam.data.ortho_scale = span
    renders = []
    for az in [-45, 0, 45]:
        a, e = math.radians(az), math.radians(12)
        cam.location = center + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * 2
        cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
        target = out / f'{label}-az{az%360:03d}.png'
        sc.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        renders.append(target.name)
    records.append({'label': label, 'source': str(source), 'source_sha256': report['source_sha256'],
                    'scene': str(folder / 'scene.blend'), 'framing': framing, 'renders': renders})
    (out / 'progress.json').write_text(json.dumps(records, indent=2) + '\n')
(out / 'report.json').write_text(json.dumps({
    'kind': 'actual_3D_detail_renders', 'cases': records,
    'same_geometry_camera_lights_material_scalars': True,
    'camera_only_heuristic': 'Front +X 30% / upper 50% bbox; not a detector or processing region',
    'art_acceptance': False,
}, indent=2) + '\n')
print('DETAIL_COMPLETE', flush=True)
