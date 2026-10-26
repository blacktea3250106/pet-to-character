"""Reimport exported candidate in the fixed review scene and render; background Blender only."""
import ast,json,math
from pathlib import Path
import bpy,bmesh,numpy as np
from mathutils import Vector,kdtree
HERE=Path(__file__).resolve().parent;ROOT=HERE/'10-style-recovery'
OUT=ROOT/'export-review';OUT.mkdir(exist_ok=True)
tree=ast.parse((HERE/'blender_stage.py').read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'bsdf','make_mat','render','export_npz','mesh_stats'}],type_ignores=[]),'review_helpers','exec'))
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'eye-material/scene.blend'))
bpy.data.objects.remove(bpy.data.objects['Cat'],do_unlink=True)
before=set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(ROOT/'eye-material/cat.glb'))
objects=[o for o in bpy.data.objects if o not in before and o.type=='MESH']
assert len(objects)==1
cat=objects[0];cat.name='RoundtripCat'
points=np.array([cat.matrix_world@v.co for v in cat.data.vertices])
original=np.load(ROOT/'clean-flat/mesh.npz')['verts']
kd=kdtree.KDTree(len(original))
for i,p in enumerate(original):kd.insert(Vector(p),i)
kd.balance();error=max(kd.find(Vector(p))[2] for p in points)
triangles=sum(len(p.vertices)-2 for p in cat.data.polygons)
assert triangles==5072 and error<1e-6
render('hero',-69,10,target=(0,0,.20),scale=.79)
render('face',-69,9,target=(.23,0,.31),scale=.28)
(OUT/'report.json').write_text(json.dumps({'glb':'../eye-material/cat.glb','mesh_count':len(objects),'triangles':triangles,'max_vertex_distance_m':float(error),'geometry_roundtrip_pass':True,'render_review_pending':True,'unity_validation':False,'art_pass':False},indent=2))
print('ROUNDTRIP_GEOMETRY_PASS',error,flush=True)
