"""Reimport a candidate GLB and reproduce its saved render views, in background Blender.

Usage: blender --background --python-exit-code 1 --python SCRIPT -- RELATIVE_CANDIDATE
This checks export fidelity only, not art, identity, rigging or target-engine acceptance.
"""
import ast, hashlib, json, math, sys
from pathlib import Path
import bpy, numpy as np
from mathutils import Vector, kdtree

HERE=Path(__file__).resolve().parent
CASE=(HERE/sys.argv[sys.argv.index('--')+1]).resolve()
assert CASE.is_relative_to(HERE)
OUT=CASE/'export-review';OUT.mkdir(exist_ok=True)
executed_source=Path(__file__).read_bytes()
(OUT/'executed-source.py').write_bytes(executed_source)
render_source=(HERE/'blender_stage.py').read_bytes()
tree=ast.parse(render_source)
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'bsdf','make_mat','render'}],type_ignores=[]),'review_helpers','exec'))
inputs=[CASE/'scene.blend',CASE/'cat.glb',CASE/'mesh.npz',CASE/'render-report.json']
provenance=[{'path':str(p.relative_to(HERE)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs]
view_report=json.loads((CASE/'render-report.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(CASE/'scene.blend'))
bpy.data.objects.remove(bpy.data.objects['Cat'],do_unlink=True)
before=set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(CASE/'cat.glb'))
objects=[o for o in bpy.data.objects if o not in before and o.type=='MESH']
assert len(objects)==1
cat=objects[0];cat.name='RoundtripCat';cat.data.calc_loop_triangles()
points=np.array([cat.matrix_world@v.co for v in cat.data.vertices])
original=np.load(CASE/'mesh.npz')
def max_distance(a,b):
    kd=kdtree.KDTree(len(b))
    for i,p in enumerate(b):kd.insert(Vector(p),i)
    kd.balance()
    return max(kd.find(Vector(p))[2] for p in a)
error=max(max_distance(points,original['verts']),max_distance(original['verts'],points))
triangles=len(cat.data.loop_triangles)
assert triangles==len(original['tris']) and error<1e-6
for name,az,el,target,scale in view_report['views']:
    render(name,az,el,target=target,scale=scale)
report={'inputs':provenance,'script_sha256':hashlib.sha256(executed_source).hexdigest(),'render_helper_sha256':hashlib.sha256(render_source).hexdigest(),'mesh_count':len(objects),'triangles':triangles,'max_symmetric_vertex_distance_m':float(error),'geometry_roundtrip_pass':True,'render_files':[v[0]+'.png' for v in view_report['views']],'render_pixel_comparison_pending':True,'unity_validation':False,'identity_or_art_pass':False,'animation_validation':False}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('CANDIDATE_ROUNDTRIP_GEOMETRY_PASS',error,flush=True)
