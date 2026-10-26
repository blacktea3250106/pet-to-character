"""Automated standing alignment and nearest-surface skin transfer baseline.

This intentionally establishes a measurable baseline, not a completed wrap.
No per-cat hand-placed joints, geometry edits, or texture changes.
"""
from pathlib import Path
import hashlib
import json
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

P = Path(__file__).resolve().parent
out = P / 'baseline-v001'
if out.exists():
    raise RuntimeError('Preserve prior baseline')
out.mkdir()
inventory = json.loads((P / 'inventory/report.json').read_text())
fit = json.loads((P / 'foot-detection.json').read_text())['affine_initialization']
source = Path(inventory['source']['path'])
target_path = Path(inventory['target']['path'])
for path, expected in [(source, inventory['source']['sha256']), (target_path, inventory['target']['sha256'])]:
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(source), use_anim=True)
source_rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
source_mesh = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
source_rig.data.pose_position = 'REST'
source_objects = set(bpy.context.scene.objects)
bpy.ops.import_scene.gltf(filepath=str(target_path))
target = next(o for o in bpy.context.scene.objects if o not in source_objects and o.type == 'MESH')
target.name = 'PersonalizedCat'
C = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
scale = np.array(fit['scale'])
offset = np.array(fit['offset'])


def mapped(p):
    return (C @ np.asarray(p)) * scale + offset


src_data = np.load(P / 'inventory/source-mesh.npz')
src_points = src_data['vertices'] @ C.T * scale + offset
tris = src_data['triangles']
weights = src_data['weights']
names = inventory['source']['vertex_groups']
tree = BVHTree.FromPolygons([Vector(v) for v in src_points], tris.tolist(), all_triangles=True)
target_points = np.array([target.matrix_world @ v.co for v in target.data.vertices])
new_weights = np.zeros((len(target_points), len(names)), np.float64)
distance = np.zeros(len(target_points))
discarded = np.zeros(len(target_points))
for i, p in enumerate(target_points):
    q, normal, face, d = tree.find_nearest(Vector(p))
    a, b, c = src_points[tris[face]]
    u, v, w = b - a, c - a, np.array(q) - a
    d00, d01, d11 = u @ u, u @ v, v @ v
    den = d00 * d11 - d01 * d01
    if abs(den) < 1e-18:
        raise ValueError('Degenerate source triangle')
    b1 = (d11 * (w @ u) - d01 * (w @ v)) / den
    b2 = (d00 * (w @ v) - d01 * (w @ u)) / den
    bary = np.maximum([1 - b1 - b2, b1, b2], 0)
    bary /= np.sum(bary)
    value = bary @ weights[tris[face]]
    if value.sum() <= 0:
        raise ValueError('Unweighted source surface')
    value /= value.sum()
    # Explicitly limit to four influences now; record discarded mass rather than
    # relying on an unknown exporter/engine truncation later.
    keep = np.argsort(value)[-4:]
    discarded[i] = 1 - value[keep].sum()
    new_weights[i, keep] = value[keep] / value[keep].sum()
    distance[i] = d

arm = bpy.data.armatures.new('PersonalizedRigData')
rig = bpy.data.objects.new('PersonalizedRig', arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
for b in source_rig.data.bones:
    eb = arm.edit_bones.new(b.name)
    rest = source_rig.matrix_world @ b.matrix_local
    rotation = C @ np.array(rest.to_3x3())
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = mapped(source_rig.matrix_world @ b.head_local)
    eb.matrix = Matrix(matrix)
    head = mapped(source_rig.matrix_world @ b.head_local)
    tail = mapped(source_rig.matrix_world @ b.tail_local)
    eb.length = max(float(np.linalg.norm(tail - head)), 1e-5)
    eb.use_deform = b.use_deform
    eb.use_connect = False
for b in source_rig.data.bones:
    if b.parent:
        arm.edit_bones[b.name].parent = arm.edit_bones[b.parent.name]
bpy.ops.object.mode_set(mode='OBJECT')
for b in source_rig.data.bones:
    arm.bones[b.name].inherit_scale = b.inherit_scale
for j, name in enumerate(names):
    group = target.vertex_groups.new(name=name)
    for i in np.flatnonzero(new_weights[:, j] > 1e-8):
        group.add([int(i)], float(new_weights[i, j]), 'REPLACE')
modifier = target.modifiers.new('TransferredSkin', 'ARMATURE')
modifier.object = rig
modifier.use_deform_preserve_volume = False
rig.show_in_front = True
for ob in source_objects:
    ob.hide_render = True
    ob.hide_set(True)
rig.data.pose_position = 'REST'
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
evaluated = target.evaluated_get(deps)
rest_points = np.array([evaluated.matrix_world @ v.co for v in evaluated.data.vertices])
assert np.max(np.abs(rest_points - target_points)) < 1e-6
target.data.calc_loop_triangles()
assert len(target.data.loop_triangles) == 3500
np.savez_compressed(out / 'weights.npz', weights=new_weights, source_distance=distance, discarded_weight_mass=discarded,
                    aligned_source_vertices=src_points, target_vertices=target_points)
report = {
    'source_sha256': inventory['source']['sha256'], 'target_sha256': inventory['target']['sha256'],
    'target_object': target.name, 'target_rig': rig.name, 'source_rig': source_rig.name, 'source_mesh': source_mesh.name,
    'canonical_rotation': C.tolist(), 'scale': scale.tolist(), 'offset': offset.tolist(),
    'bone_names': [b.name for b in arm.bones], 'weight_groups': names,
    'source_to_target_distance': {str(p): float(np.percentile(distance, p)) for p in [50, 90, 95, 100]},
    'discarded_mass_four_influences': {str(p): float(np.percentile(discarded, p)) for p in [50, 95, 100]},
    'rest_vertex_max_delta': float(np.max(np.abs(rest_points - target_points))),
    'triangles': len(target.data.loop_triangles), 'animations_baked': False,
    'limitations': ['Affine standing alignment does not model curled tail or target anatomy.',
                   'Nearest-surface skin transfer can assign weights to a nearby wrong body part.',
                   'Copying rest orientations preserves the source rotation convention but does not prove target joint centers.'],
    'art_pass': False, 'animation_pass': False, 'new_cat_automation_proven': False
}
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'rigged-rest.blend'))
print(json.dumps({'triangles': 3500, 'bones': len(arm.bones), 'distance': report['source_to_target_distance'], 'discarded_mass': report['discarded_mass_four_influences']}), flush=True)
