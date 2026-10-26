"""Bake selected source rotations to fitted rig and measure every sampled frame."""
from pathlib import Path
import argparse
import json
import sys
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

P = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('candidate')
parser.add_argument('--checkpoints-only', action='store_true', help='Diagnostic first/middle/last only; never full animation acceptance')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = P / args.candidate
if (out / 'animation-report.json').exists():
    raise RuntimeError('Do not overwrite prior animation evidence')
cfg = json.loads((P / 'action_gate.json').read_text())
report = json.loads((out / 'report.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(out / 'rigged-rest.blend'))
sc = bpy.context.scene
sc.render.fps = 30
target = bpy.data.objects[report['target_object']]
rig = bpy.data.objects[report['target_rig']]
src = bpy.data.objects[report['source_rig']]
src_mesh = bpy.data.objects[report['source_mesh']]
source_actions = {a.name.split('|')[-1]: a for a in list(bpy.data.actions) if '|' in a.name}
C, scale, offset = np.array(report['canonical_rotation']), np.array(report['scale']), np.array(report['offset'])
src_world_rest = src.matrix_world.copy()
rig.data.pose_position = 'POSE'
src.data.pose_position = 'POSE'
rig.animation_data_create()
src.animation_data_create()
target.data.calc_loop_triangles()
src_mesh.data.calc_loop_triangles()
triangles = {'target': np.array([t.vertices[:] for t in target.data.loop_triangles], np.int32),
             'source': np.array([t.vertices[:] for t in src_mesh.data.loop_triangles], np.int32)}
rest = {'target': np.array([target.matrix_world @ v.co for v in target.data.vertices]),
        'source': np.array([src_mesh.matrix_world @ v.co for v in src_mesh.data.vertices]) @ C.T * scale + offset}
ground = float(rest['target'][:, 2].min())
body_length = float(np.ptp(rest['target'], axis=0).max())
topology = {}
for name in ['source', 'target']:
    _, weld = np.unique(np.rint(rest[name] / (body_length * 1e-7)).astype(np.int64), axis=0, return_inverse=True)
    f = triangles[name]
    e = np.unique(np.sort(np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1), axis=0)
    l = np.linalg.norm(rest[name][e[:, 0]] - rest[name][e[:, 1]], axis=1)
    keep = l > body_length * 1e-8
    area = np.linalg.norm(np.cross(rest[name][f[:, 1]] - rest[name][f[:, 0]], rest[name][f[:, 2]] - rest[name][f[:, 0]]), axis=1)
    topology[name] = {'weld': weld[f], 'edges': e[keep], 'lengths': l[keep], 'areas': area}


def segment_hit(a, b, tri):
    # Strict segment/interior crossing. Tangent/coplanar contacts excluded.
    eps = 1e-6
    direction = b - a
    e1, e2 = tri[1] - tri[0], tri[2] - tri[0]
    h = np.cross(direction, e2)
    det = e1 @ h
    if abs(det) < body_length ** 3 * 1e-12:
        return False
    inv = 1 / det
    s = a - tri[0]
    u = inv * (s @ h)
    if not eps < u < 1 - eps:
        return False
    q = np.cross(s, e1)
    v = inv * (direction @ q)
    if v <= eps or u + v >= 1 - eps:
        return False
    t = inv * (e2 @ q)
    return eps < t < 1 - eps


def measure(name, points):
    f, t = triangles[name], topology[name]
    tree = BVHTree.FromPolygons([Vector(v) for v in points], f.tolist(), all_triangles=True)
    candidates = tree.overlap(tree)
    crossing = []
    for i, j in candidates:
        if i >= j or np.isin(t['weld'][i], t['weld'][j]).any():
            continue
        a, b = points[f[i]], points[f[j]]
        hit = any(segment_hit(a[k], a[(k+1)%3], b) or segment_hit(b[k], b[(k+1)%3], a) for k in range(3))
        if hit:
            crossing.append([int(i), int(j)])
    ratio = np.linalg.norm(points[t['edges'][:, 0]] - points[t['edges'][:, 1]], axis=1) / t['lengths']
    area = np.linalg.norm(np.cross(points[f[:, 1]] - points[f[:, 0]], points[f[:, 2]] - points[f[:, 0]]), axis=1)
    area_ratio = area / np.maximum(t['areas'], body_length**2 * 1e-12)
    return {'lowest_relative_to_ground': float(points[:, 2].min() - ground),
            'vertices_below_1pct_extent': int((points[:, 2] < ground - .01 * body_length).sum()),
            'nonadjacent_crossing_pairs': len(crossing), 'crossing_face_ids': crossing,
            'max_edge_stretch': float(ratio.max()), 'edges_stretched_over_2x': int((ratio > 2).sum()),
            'faces_area_below_30pct': int((area_ratio < .3).sum())}


actions_report = []
baked_actions = []
for short in cfg['core_actions']:
    action = source_actions[short]
    src.animation_data.action = action
    src.animation_data.action_slot = action.slots[0]
    new = bpy.data.actions.new(short)
    new.use_fake_user = True
    rig.animation_data.action = new
    source_frames = range(int(action.frame_range[0]), int(action.frame_range[1]) + 1)
    checkpoint_frames = sorted({source_frames.start, source_frames.stop - 1, (source_frames.start + source_frames.stop - 1)//2})
    frames = checkpoint_frames if args.checkpoints_only else source_frames
    samples, source_objects_delta = [], []
    frozen = {}
    for frame in frames:
        sc.frame_set(frame)
        delta_object = src.matrix_world @ src_world_rest.inverted()
        object_difference = float(np.max(np.abs(np.array(delta_object) - np.eye(4))))
        source_objects_delta.append(object_difference)
        if object_difference > 1e-4:
            raise RuntimeError('Source armature object motion needs explicit retargeting, not silent omission')
        for bone in rig.pose.bones:
            original = src.pose.bones[bone.name]
            loc, rotation, sizes = original.matrix_basis.decompose()
            # New rest orientations equal canonicalized source rest orientations.
            rest_rotation = C @ np.array((src_world_rest @ src.data.bones[bone.name].matrix_local).to_3x3())
            translated = rest_rotation.T @ np.diag(scale) @ rest_rotation @ np.asarray(loc)
            bone.rotation_mode = 'QUATERNION'
            bone.location = Vector(translated)
            bone.rotation_quaternion = rotation
            bone.scale = sizes
            for channel in ['location', 'rotation_quaternion', 'scale']:
                bone.keyframe_insert(data_path=channel, frame=frame, group=bone.name)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        tv = target.evaluated_get(deps)
        sv = src_mesh.evaluated_get(deps)
        target_points = np.array([tv.matrix_world @ v.co for v in tv.data.vertices])
        source_points = np.array([sv.matrix_world @ v.co for v in sv.data.vertices]) @ C.T * scale + offset
        metric = {'frame': frame, 'source': measure('source', source_points), 'target': measure('target', target_points)}
        samples.append(metric)
        if frame in checkpoint_frames:
            frozen[str(frame)] = target_points.astype(np.float32)
    name = short.replace('/', '_')
    (out / f'{name}-frames.json').write_text(json.dumps(samples, separators=(',', ':')) + '\n')
    np.savez_compressed(out / f'{name}-checkpoints.npz', **frozen)
    metrics = {}
    for label in ['source', 'target']:
        metrics[label] = {key: max(s[label][key] for s in samples) for key in ['nonadjacent_crossing_pairs', 'max_edge_stretch', 'edges_stretched_over_2x', 'faces_area_below_30pct', 'vertices_below_1pct_extent']}
        metrics[label]['lowest_relative_to_ground'] = min(s[label]['lowest_relative_to_ground'] for s in samples)
        metrics[label]['worst_crossing_frame'] = max(samples, key=lambda s: s[label]['nonadjacent_crossing_pairs'])['frame']
    summary = {'action': short, 'frames': len(samples), 'range': [source_frames.start, source_frames.stop - 1], 'metrics': metrics,
               'source_object_motion_max_delta': max(source_objects_delta)}
    actions_report.append(summary)
    baked_actions.append(new)
    print(json.dumps(summary), flush=True)

for ob in list(bpy.context.selected_objects):
    ob.select_set(False)
target.hide_set(False)
rig.hide_set(False)
target.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
rig.animation_data.action = baked_actions[0]
rig.animation_data.action_slot = baked_actions[0].slots[0]
sc.frame_set(1)
result = {'candidate': args.candidate, 'actions': actions_report, 'fps': 30, 'ground': ground, 'extent': body_length,
          'coverage': 'first_middle_last_only' if args.checkpoints_only else 'every_integer_frame',
          'collision_method': 'BVH candidate pairs, exclude shared welded vertices, strict edge/triangle interior crossings; tangent and coplanar contacts excluded.',
          'limits': ['Intersection counts do not measure penetration depth or all contacts.',
                     'Ground metrics use current static input ground; root/foot IK not applied.',
                     'Edge/area ratios are relative to the input rest mesh, not an aesthetic verdict.',
                     'Foot sliding not scored: source support phases/root travel not yet calibrated.'],
          'animation_pass': False, 'unity_pass': False, 'new_cat_automation_proven': False}
(out / 'animation-report.json').write_text(json.dumps(result, indent=2) + '\n')
(out / 'executed-animation-source.py').write_bytes(Path(__file__).read_bytes())
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'animated.blend'))
print('ANIMATION_MEASUREMENT_COMPLETE', flush=True)
