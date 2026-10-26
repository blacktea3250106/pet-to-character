"""Automated standing alignment and nearest-surface skin transfer baseline.

This intentionally establishes a measurable baseline, not a completed wrap.
No per-cat hand-placed joints, geometry edits, or texture changes.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

P = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--output', default='baseline-v002')
parser.add_argument('--influences', type=int, default=4)
parser.add_argument('--smooth-iterations', type=int, default=0)
parser.add_argument('--smooth-factor', type=float, default=.35)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
out = P / args.output
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
    new_weights[i] = value
    distance[i] = d

if args.smooth_iterations:
    target.data.calc_loop_triangles()
    target_tris = np.array([t.vertices[:] for t in target.data.loop_triangles], np.int32)
    span = np.ptp(target_points, axis=0).max()
    _, welded = np.unique(np.rint(target_points / (span * 1e-7)).astype(np.int64), axis=0, return_inverse=True)
    unique_count = welded.max() + 1
    combined = np.zeros((unique_count, len(names)))
    np.add.at(combined, welded, new_weights)
    combined /= np.bincount(welded)[:, None]
    f = welded[target_tris]
    edges = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    edges = edges[edges[:, 0] != edges[:, 1]]
    directed = np.vstack([edges, edges[:, ::-1]])
    degree = np.bincount(directed[:, 0], minlength=unique_count)
    assert (degree > 0).all()
    for _ in range(args.smooth_iterations):
        neighbor = np.zeros_like(combined)
        np.add.at(neighbor, directed[:, 0], combined[directed[:, 1]])
        combined = (1-args.smooth_factor)*combined + args.smooth_factor*neighbor/degree[:, None]
    new_weights = combined[welded]
unpruned = new_weights.copy()
for i, value in enumerate(unpruned):
    keep = np.argsort(value)[-args.influences:]
    discarded[i] = 1 - value[keep].sum()
    new_weights[i] = 0
    new_weights[i, keep] = value[keep] / value[keep].sum()

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
    head = mapped(source_rig.matrix_world @ b.head_local)
    tail = mapped(source_rig.matrix_world @ b.tail_local)
    length = max(float(np.linalg.norm(tail - head)), 1e-5)
    # Newly created edit bones have zero length. Setting matrix before a valid
    # head/tail loses their direction; initialize the intended axis explicitly.
    direction = rotation[:, 1] / np.linalg.norm(rotation[:, 1])
    eb.head = Vector(head)
    eb.tail = Vector(head + direction * length)
    eb.align_roll(Vector(rotation[:, 2]))
    eb.use_deform = b.use_deform
    eb.use_connect = False
for b in source_rig.data.bones:
    if b.parent:
        arm.edit_bones[b.name].parent = arm.edit_bones[b.parent.name]
bpy.ops.object.mode_set(mode='OBJECT')
rotation_errors = {}
for b in source_rig.data.bones:
    arm.bones[b.name].inherit_scale = b.inherit_scale
    expected = C @ np.array((source_rig.matrix_world @ b.matrix_local).to_3x3())
    actual = np.array(arm.bones[b.name].matrix_local.to_3x3())
    rotation_errors[b.name] = float(np.max(np.abs(expected - actual)))
assert max(rotation_errors.values()) < 1e-4, 'Rest orientation mismatch'
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
    'max_influences': args.influences,
    'smoothing': {'iterations': args.smooth_iterations, 'factor': args.smooth_factor, 'domain': 'welded analysis topology only'},
    'discarded_mass_after_pruning': {str(p): float(np.percentile(discarded, p)) for p in [50, 95, 100]},
    'rest_vertex_max_delta': float(np.max(np.abs(rest_points - target_points))),
    'rest_orientation_max_abs_error': max(rotation_errors.values()),
    'triangles': len(target.data.loop_triangles), 'animations_baked': False,
    'limitations': ['Affine standing alignment does not model curled tail or target anatomy.',
                   'Nearest-surface skin transfer can assign weights to a nearby wrong body part.',
                   'Copying rest orientations preserves the source rotation convention but does not prove target joint centers.'],
    'art_pass': False, 'animation_pass': False, 'new_cat_automation_proven': False
}
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'rigged-rest.blend'))
print(json.dumps({'triangles': 3500, 'bones': len(arm.bones), 'distance': report['source_to_target_distance'], 'discarded_mass': report['discarded_mass_after_pruning']}), flush=True)
