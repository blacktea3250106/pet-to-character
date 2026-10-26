from pathlib import Path
import json
import bpy
import numpy as np
from mathutils.kdtree import KDTree

P=Path(__file__).resolve().parent/'weights-v001'
bpy.ops.wm.open_mainfile(filepath=str(P/'animated.blend'))
cat=bpy.data.objects['PersonalizedCat']
pts=np.array([cat.matrix_world@v.co for v in cat.data.vertices])
source_matrix=np.array(cat.matrix_world).tolist()
tree=KDTree(len(pts))
for i,v in enumerate(pts):tree.insert(v,i)
tree.balance()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps=30
bpy.ops.import_scene.gltf(filepath=str(P/'export-rejected-v001/cat-animated.glb'))
cat=next(o for o in bpy.context.scene.objects if o.type=='MESH')
dst=np.array([cat.matrix_world@v.co for v in cat.data.vertices])
dist=np.array([tree.find(v)[2] for v in dst])
info={'source_matrix':source_matrix,'dest_matrix':np.array(cat.matrix_world).tolist(),'source_bounds':[pts.min(0).tolist(),pts.max(0).tolist()], 'dest_bounds':[dst.min(0).tolist(),dst.max(0).tolist()], 'distance_max':float(dist.max()),'distance_quantiles':np.quantile(dist,[.5,.95,1]).tolist(),'imported_actions':[{'name':a.name,'range':list(a.frame_range)} for a in bpy.data.actions]}
(P/'export-rejected-v001/probe.json').write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps(info),flush=True)
