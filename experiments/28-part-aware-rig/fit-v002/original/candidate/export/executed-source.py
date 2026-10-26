"""Export only the five selected clips, then verify actual imported skin deformation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

P = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument('candidate')
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
folder = P / args.candidate
out = folder / 'export'
if out.exists():
    raise RuntimeError('Preserve prior export evidence')
out.mkdir()
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
report = json.loads((folder / 'report.json').read_text())
selected = json.loads((P / 'action_gate.json').read_text())['core_actions']
bpy.ops.wm.open_mainfile(filepath=str(folder / 'animated.blend'))
cat = bpy.data.objects[report['target_object']]
rig = bpy.data.objects[report['target_rig']]
for ob in list(bpy.data.objects):
    if ob not in (cat, rig):
        bpy.data.objects.remove(ob, do_unlink=True)
for action in list(bpy.data.actions):
    if action.name not in selected:
        bpy.data.actions.remove(action, do_unlink=True)
assert sorted(a.name for a in bpy.data.actions) == sorted(selected)
sc = bpy.context.scene
sc.render.fps = 30


def rest_points(ob):
    return np.array([ob.matrix_world @ v.co for v in ob.data.vertices], dtype=np.float64)


def corners(ob):
    ob.data.calc_loop_triangles()
    points = rest_points(ob)
    uv = ob.data.uv_layers.active
    rows = []
    for tri in ob.data.loop_triangles:
        for li in tri.loops:
            vi = ob.data.loops[li].vertex_index
            rows.append([*points[vi], *uv.data[li].uv])
    return np.asarray(rows)


def corner_distance(a, b):
    # Sorting quantized coordinates is unstable when float roundoff crosses a bin.
    # Match spatial neighbors, then compare UVs; check both directions below.
    tree = KDTree(len(a))
    for i, row in enumerate(a):
        tree.insert(Vector(row[:3]), i)
    tree.balance()
    errors = []
    for row in b:
        neighbors = tree.find_range(Vector(row[:3]), 1e-5)
        if not neighbors:
            return float('inf')
        ids = [n[1] for n in neighbors]
        errors.append(float(np.min(np.max(np.abs(a[ids] - row), axis=1))))
    return max(errors)


def image_pixels(ob):
    material = ob.data.materials[0]
    bsdf = next(n for n in material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    link = next(l for l in material.node_tree.links if l.to_node == bsdf and l.to_socket.name == 'Base Color')
    tex = link.from_node.image
    pixels = np.empty(len(tex.pixels), dtype=np.float32)
    tex.pixels.foreach_get(pixels)
    return pixels, {'size': list(tex.size), 'color_space': tex.colorspace_settings.name,
                    'metallic': float(bsdf.inputs['Metallic'].default_value),
                    'roughness': float(bsdf.inputs['Roughness'].default_value),
                    'ior_specular': float(bsdf.inputs['Specular IOR Level'].default_value)}


original_points = rest_points(cat)
original_corners = corners(cat)
original_pixels, original_material = image_pixels(cat)
tree = KDTree(len(original_points))
for i, p in enumerate(original_points):
    tree.insert(Vector(p), i)
tree.balance()
for ob in list(bpy.context.selected_objects):
    ob.select_set(False)
for ob in (cat, rig):
    ob.hide_set(False)
    ob.hide_render = False
    ob.select_set(True)
bpy.context.view_layer.objects.active = rig
world_matrix = cat.matrix_world.copy()
cat.parent = rig
cat.matrix_world = world_matrix
rig.data.pose_position = 'POSE'
rig.animation_data.action = bpy.data.actions['Idle']
rig.animation_data.action_slot = rig.animation_data.action.slots[0]
sc.frame_set(1)
influences = report.get('max_influences', 4)
path = out / 'cat-animated.glb'
bpy.ops.export_scene.gltf(
    filepath=str(path), export_format='GLB', use_selection=True,
    export_animations=True, export_animation_mode='ACTIONS',
    export_frame_range=False, export_force_sampling=True,
    export_anim_single_armature=True, export_anim_slide_to_zero=True,
    export_skins=True, export_influence_nb=influences,
    export_all_influences=False, export_rest_position_armature=True,
    export_image_format='AUTO', export_keep_originals=False,
)
raw = path.read_bytes()
length, kind = struct.unpack_from('<II', raw, 12)
assert kind == 0x4E4F534A
gltf = json.loads(raw[20:20 + length])
names = [a.get('name') for a in gltf.get('animations', [])]
assert sorted(names) == sorted(selected), names
triangles = sum(gltf['accessors'][p['indices']]['count'] // 3 for m in gltf['meshes'] for p in m['primitives'])
assert triangles == 3500
assert len(gltf.get('skins', [])) == 1
attributes = [sorted(p['attributes']) for m in gltf['meshes'] for p in m['primitives']]
assert all('JOINTS_0' in a and 'WEIGHTS_0' in a for a in attributes)
if influences == 8:
    assert all('JOINTS_1' in a and 'WEIGHTS_1' in a for a in attributes)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = 30
bpy.ops.import_scene.gltf(filepath=str(path))
cat2 = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
rig2 = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
rest2 = rest_points(cat2)
nearest = [tree.find(Vector(p)) for p in rest2]
mapping = np.array([n[1] for n in nearest])
rest_error = max(n[2] for n in nearest)
corner2 = corners(cat2)
assert corner2.shape == original_corners.shape
corner_error = max(corner_distance(original_corners, corner2), corner_distance(corner2, original_corners))
pixels2, material2 = image_pixels(cat2)
assert pixels2.shape == original_pixels.shape
pixel_error = float(np.max(np.abs(pixels2 - original_pixels)))
print('REST_AND_TEXTURE_ERRORS', rest_error, corner_error, pixel_error, flush=True)
assert rest_error < 1e-5 and corner_error < 1e-5
assert pixel_error < 1e-5, pixel_error
assert original_material == material2, (original_material, material2)
actions = {a.name: a for a in bpy.data.actions}
assert sorted(actions) == sorted(selected), list(actions)
rig2.animation_data_create()
samples = []
for name in selected:
    action = actions[name]
    rig2.animation_data.action = action
    rig2.animation_data.action_slot = action.slots[0]
    checkpoints = np.load(folder / f'{name}-checkpoints.npz')
    original_first = 1
    imported_first = float(action.frame_range[0])
    for key in checkpoints.files:
        frame = float(key) - original_first + imported_first
        bpy.context.scene.frame_set(int(round(frame)))
        bpy.context.view_layer.update()
        evaluated = cat2.evaluated_get(bpy.context.evaluated_depsgraph_get())
        points = np.array([evaluated.matrix_world @ v.co for v in evaluated.data.vertices])
        errors = np.linalg.norm(points - checkpoints[key][mapping], axis=1)
        sample = {'action': name, 'original_frame': int(key), 'imported_frame': frame,
                  'max_vertex_error': float(errors.max()), 'mean_vertex_error': float(errors.mean())}
        samples.append(sample)
        print(json.dumps(sample), flush=True)
result = {
    'candidate': args.candidate, 'file': path.name,
    'sha256': hashlib.sha256(raw).hexdigest(), 'triangles': triangles,
    'skin_count': len(gltf['skins']), 'joint_count': len(gltf['skins'][0]['joints']),
    'animations': names, 'max_influences': influences, 'attributes': attributes,
    'rest_nearest_vertex_max_error': rest_error, 'rest_corner_position_uv_max_error': corner_error,
    'decoded_texture_max_error': pixel_error, 'material': material2,
    'deformation_checkpoints': samples,
    'max_deformation_error': max(s['max_vertex_error'] for s in samples),
    'export_roundtrip_pass': max(s['max_vertex_error'] for s in samples) < 1e-4,
    'animation_quality_pass': False, 'unity_pass': False,
    'limits': ['Roundtrip tests first/middle/last of each clip, not every interpolated time.',
               'Skin weights and material extensions still need Unity importer/runtime verification.',
               'Correct export preserves the existing measured animation defects; it does not fix them.'],
}
(out / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'reimported.blend'))
assert result['export_roundtrip_pass'], result['max_deformation_error']
print('EXPORT_ROUNDTRIP_VERIFIED', flush=True)
