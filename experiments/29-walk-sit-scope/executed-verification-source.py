"""Read selected GLB and compare the four retained actions at 12 real poses."""
import json
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

P=Path(__file__).resolve().parent;prior=P.parent/'27-animation-compatibility/weights-v001'
selection=json.loads((P/'selection.json').read_text())
points=np.load(prior/'weights.npz')['target_vertices']
tree=KDTree(len(points))
for i,p in enumerate(points):tree.insert(Vector(p),i)
tree.balance()
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=30
bpy.ops.import_scene.gltf(filepath=str(P/selection['output']))
mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH');rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
rest=np.array([mesh.matrix_world@v.co for v in mesh.data.vertices]);near=[tree.find(Vector(v)) for v in rest];mapping=np.array([v[1] for v in near])
assert max(v[2] for v in near)<1e-5
assert sorted(a.name for a in bpy.data.actions)==sorted(selection['clips'])
mesh.data.calc_loop_triangles();assert len(mesh.data.loop_triangles)==3500 and len(rig.data.bones)==56
rig.animation_data_create();samples=[]
for name in selection['clips']:
    action=bpy.data.actions[name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
    checkpoints=np.load(prior/f'{name}-checkpoints.npz')
    for key in checkpoints.files:
        frame=int(key)-1+int(round(action.frame_range[0]));bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get());v=np.array([evaluated.matrix_world@v.co for v in evaluated.data.vertices])
        error=np.linalg.norm(v-checkpoints[key][mapping],axis=1)
        samples.append({'clip':name,'source_frame':int(key),'imported_frame':frame,'max_vertex_error':float(error.max())})
report={'clips':selection['clips'],'poses_checked':len(samples),'samples':samples,'max_vertex_error':max(s['max_vertex_error'] for s in samples),
        'roundtrip_pass':max(s['max_vertex_error'] for s in samples)<1e-4,'animation_quality_pass':False,'unity_pass':False}
(P/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
(P/'executed-verification-source.py').write_bytes(Path(__file__).read_bytes())
assert report['roundtrip_pass']
print(json.dumps({'poses':len(samples),'max_error':report['max_vertex_error'],'roundtrip_pass':True}),flush=True)
