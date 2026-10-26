"""Produce a separate ~3500-triangle candidate; protect manually identified head/paws.

Run only in background Blender. Region definitions are case-specific, not automatic rig anatomy.
"""
import ast, hashlib, json, math, time
from pathlib import Path
import bpy, bmesh, numpy as np
from mathutils import Vector, kdtree
from mathutils.bvhtree import BVHTree

HERE=Path(__file__).resolve().parent
ROOT=HERE/'14-budget-3500';OUT=ROOT/'weighted-v001';OUT.mkdir(parents=True,exist_ok=True)
source=HERE/'13-dorsal/color-v002/scene.blend'
executed_source=Path(__file__).read_bytes();(OUT/'executed-source.py').write_bytes(executed_source)
tree=ast.parse((HERE/'blender_stage.py').read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'bsdf','make_mat','render','export_npz','mesh_stats'}],type_ignores=[]),'render_helpers','exec'))
bpy.ops.wm.open_mainfile(filepath=str(source))
cat=bpy.data.objects['Cat'];bpy.context.view_layer.objects.active=cat;cat.select_set(True)
original=np.load(source.parent/'mesh.npz');v,t=original['verts'],original['tris']
assert len(t)==5072
render('baseline-face',-69,9,target=(.23,0,.31),scale=.28)
render('baseline-opposite-clay',110,10,target=(0,0,.20),scale=.79,clay=True)

head=(v[:,0]>.15)&(v[:,2]>.18)
paws=v[:,2]<.055
protected=head|paws
weights=np.ones(len(v),float)
weights[v[:,2]<.20]=.25
weights[v[:,0]<-.17]=.35
weights[protected]=0
group=cat.vertex_groups.new(name='Case_Decimation_Allowance')
for i,w in enumerate(weights):group.add([i],float(w),'REPLACE')
mod=cat.modifiers.new('Target3500','DECIMATE');mod.decimate_type='COLLAPSE'
mod.ratio=(3500+.25)/len(t);mod.use_collapse_triangulate=True
mod.vertex_group=group.name;mod.vertex_group_factor=1.0;mod.use_symmetry=False
started=time.monotonic()
bpy.ops.object.modifier_apply(modifier=mod.name)
seconds=time.monotonic()-started
cat.data.calc_loop_triangles()
triangles=len(cat.data.loop_triangles)
assert 3496<=triangles<=3500,triangles
for face in cat.data.polygons:face.use_smooth=False
export_npz(cat,OUT/'mesh.npz');new=np.load(OUT/'mesh.npz')
nv,nt=new['verts'],new['tris']
kd=kdtree.KDTree(len(nv))
for i,p in enumerate(nv):kd.insert(Vector(p),i)
kd.balance()
protected_error=max(kd.find(Vector(p))[2] for p in v[protected]);assert protected_error<1e-7,protected_error
def sample_distances(vertices,tris,ref_vertices,ref_tris):
    # Vertices plus face centers: diagnostic samples, not a continuous Hausdorff bound.
    samples=np.concatenate([vertices,vertices[tris].mean(1)])
    bvh=BVHTree.FromPolygons([Vector(p) for p in ref_vertices],ref_tris.tolist(),all_triangles=True)
    return np.array([bvh.find_nearest(Vector(p))[3] for p in samples])
forward=sample_distances(v,t,nv,nt);reverse=sample_distances(nv,nt,v,t)
stats=mesh_stats(cat)
assert stats['boundary_edges']==0 and stats['nonmanifold_edges']==0
assert np.isfinite(new['tri_uv']).all()
report={
 'source':str(source.relative_to(HERE)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'script_sha256':hashlib.sha256(executed_source).hexdigest(),
 'method':'Blender Decimate COLLAPSE with weighted allowance; flat shading and existing color/roughness textures retained',
 'official_reference':'https://docs.blender.org/UATEST/manual/en/dev/modeling/modifiers/generate/decimate.html',
 'requested_triangles':3500,'source_triangles':len(t),'actual_triangles':triangles,
 'reduction_fraction':1-triangles/len(t),'modifier_seconds':seconds,
 'manual_regions':{'protected_head':'x > 0.15 and z > 0.18 metres','protected_paws':'z < 0.055 metres','leg_weight':'0.25 below z=0.20','tail_weight':'0.35 below x=-0.17','else_weight':1.0,'coordinate_system':'current normalized and manually oriented case','protected_vertices':int(protected.sum())},
 'protected_original_vertex_max_distance_m':float(protected_error),
 'sampled_surface_distance_m':{'source_to_candidate_max':float(forward.max()),'candidate_to_source_max':float(reverse.max()),'source_to_candidate_p95':float(np.percentile(forward,95)),'candidate_to_source_p95':float(np.percentile(reverse,95)),'scope':'vertices and face-centers only; not a full surface maximum or deformation test'},
 'stats':stats,'topology_changed':True,'uv_layout_repacked':False,'uv_interpolation_changed':True,
 'invalidated_data':['prior triangle IDs and barycentric correspondences','prior geometry QA and any deformation assumptions'],
 'animation_compatibility':'not_tested; source and candidate are unrigged',
 'new_cat_automation_proven':False,'identity_or_art_pass':False,'manual_review_pending':True,
 'views':[['hero',-69,10,[0,0,.20],.79],['face',-69,9,[.23,0,.31],.28],['opposite',110,10,[0,0,.20],.79],['back-high',110,48,[0,0,.20],.79]],
 'limitations':['Protected areas were manually defined for this case.','No semantic joint rings or deformation tests are available; 3500 triangles does not prove animation compatibility.','Decimation does not necessarily remove existing folded flank geometry.','Texture reprojection after this step must rebuild mappings using the new mesh.']
}
for name,az,el,target,scale in report['views']:render(name,az,el,target=target,scale=scale)
render('opposite-clay',110,10,target=(0,0,.20),scale=.79,clay=True)
(OUT/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);bpy.context.view_layer.objects.active=cat
bpy.ops.export_scene.gltf(filepath=str(OUT/'cat.glb'),export_format='GLB',use_selection=True)
print('BUDGET_CANDIDATE_COMPLETE',triangles,'triangles',seconds,'seconds to decimate',flush=True)
