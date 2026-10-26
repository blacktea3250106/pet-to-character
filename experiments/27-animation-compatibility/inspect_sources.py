"""Read source FBX and target GLB into an isolated scene; export inventory."""
from pathlib import Path
import hashlib
import json
import bpy
import numpy as np
from mathutils import Vector

P = Path(__file__).resolve().parent
SOURCE = P.parent.parent / 'texture-transfer-v001/source/SKM_Cat_Domestic_Shorthair.fbx'
TARGET = P.parent / '25-appearance-diagnostic/matte-candidate/cat.glb'
out = P / 'inventory'
if out.exists():
    raise RuntimeError('Preserve previous inventory')
out.mkdir()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(SOURCE), use_anim=True)
rigs = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
assert len(rigs) == 1
rig = rigs[0]
mesh = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
rig.data.pose_position = 'REST'
mesh.data.calc_loop_triangles()
names = [g.name for g in mesh.vertex_groups]
weights = np.zeros((len(mesh.data.vertices), len(names)), np.float32)
for v in mesh.data.vertices:
    for g in v.groups:
        weights[v.index, g.group] = g.weight
points = np.array([mesh.matrix_world @ v.co for v in mesh.data.vertices])
triangles = np.array([t.vertices[:] for t in mesh.data.loop_triangles], np.int32)
bones = [{'name': b.name, 'parent': b.parent.name if b.parent else None,
          'deform': b.use_deform, 'head': list(rig.matrix_world @ b.head_local),
          'tail': list(rig.matrix_world @ b.tail_local),
          'rest_world': [list(row) for row in rig.matrix_world @ b.matrix_local]}
         for b in rig.data.bones]
actions = []
for a in bpy.data.actions:
    channels = []
    for layer in a.layers:
        for strip in layer.strips:
            for slot in a.slots:
                bag = strip.channelbag(slot, ensure=False)
                if bag:
                    channels.extend([{'path': f.data_path, 'index': f.array_index, 'keys': len(f.keyframe_points)} for f in bag.fcurves])
    actions.append({'name': a.name, 'short_name': a.name.split('|')[-1], 'frame_range': list(a.frame_range),
                    'slots': [s.identifier for s in a.slots], 'channels': channels})
np.savez_compressed(out / 'source-mesh.npz', vertices=points, triangles=triangles, weights=weights)
src_objects = set(bpy.context.scene.objects)
bpy.ops.import_scene.gltf(filepath=str(TARGET))
target = next(o for o in bpy.context.scene.objects if o not in src_objects and o.type == 'MESH')
target.data.calc_loop_triangles()
tpoints = np.array([target.matrix_world @ v.co for v in target.data.vertices])
ttris = np.array([t.vertices[:] for t in target.data.loop_triangles], np.int32)
np.savez_compressed(out / 'target-mesh.npz', vertices=tpoints, triangles=ttris)
report = {
    'source': {'path': str(SOURCE), 'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
               'mesh_name': mesh.name, 'rig_name': rig.name, 'vertex_groups': names,
               'vertices': len(points), 'triangles': len(triangles), 'bounds': [points.min(0).tolist(), points.max(0).tolist()],
               'bones': bones, 'actions': actions, 'fps': bpy.context.scene.render.fps,
               'rig_world_matrix': [list(row) for row in rig.matrix_world]},
    'target': {'path': str(TARGET), 'sha256': hashlib.sha256(TARGET.read_bytes()).hexdigest(),
               'vertices': len(tpoints), 'triangles': len(ttris), 'bounds': [tpoints.min(0).tolist(), tpoints.max(0).tolist()]},
    'blender': bpy.app.version_string
}
(out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'source_bones': len(bones), 'source_triangles': len(triangles), 'actions': [(a['short_name'], a['frame_range']) for a in actions], 'source_bounds': report['source']['bounds'], 'target_bounds': report['target']['bounds']}), flush=True)
