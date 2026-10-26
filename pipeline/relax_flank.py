"""Single-case local shape correction, defined in an inspected rendered view; no topology changes."""
import ast,json,math,hashlib,sys
from pathlib import Path
import bpy,bmesh,numpy as np
from mathutils import Vector
HERE=Path(__file__).resolve().parent;FULL='--full' in sys.argv
OUT=HERE/'11-other-side'/('flank-relax-v2' if FULL else 'flank-relax');OUT.mkdir(exist_ok=True)
tree=ast.parse((HERE/'blender_stage.py').read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'bsdf','make_mat','render','export_npz','mesh_stats'}],type_ignores=[]),'review_helpers','exec'))
source=HERE/'10-style-recovery/eye-material/scene.blend'
bpy.ops.wm.open_mainfile(filepath=str(source));cat=bpy.data.objects['Cat'];me=cat.data
v=np.array([x.co[:] for x in me.vertices]);norm=np.array([x.normal[:] for x in me.vertices])
az,el=np.deg2rad([110,10]);direction=np.array([np.cos(az)*np.cos(el),np.sin(az)*np.cos(el),np.sin(el)])
right=np.array([-np.sin(az),np.cos(az),0]);up=np.cross(direction,right)
center=np.array([0,0,.20]);scale=1200/.79
q=np.column_stack([600+scale*((v-center)@right),450-scale*((v-center)@up)])
# Visually identified gill-like ridges above the left hip. Elliptic falloff avoids a hard ROI border.
rad=np.sqrt(((q[:,0]-640)/145)**2+((q[:,1]-395)/190)**2)
weight=np.clip((1-rad)/.4,0,1)*(np.clip((v[:,1]-.02)/.025,0,1) if FULL else np.clip((norm@direction-.15)/.4,0,1))
neighbors=[set() for _ in v]
for e in me.edges:
    a,b=e.vertices;neighbors[a].add(b);neighbors[b].add(a)
old=v.copy()
iterations=10 if FULL else 5
cap=.009 if FULL else .004
for _ in range(iterations):
    avg=np.array([v[list(n)].mean(0) if n else v[i] for i,n in enumerate(neighbors)])
    # Only normal displacement. No tangential topology redistribution or large silhouette change.
    delta=avg-v;normal_delta=np.sum(delta*norm,1)[:,None]*norm
    v+=.45*weight[:,None]*(delta if FULL else normal_delta)
    total=v-old;length=np.linalg.norm(total,axis=1)
    v=old+total*np.minimum(1,cap/np.maximum(length,1e-12))[:,None]
for vertex,p in zip(me.vertices,v):vertex.co=Vector(p)
me.update()
report={'purpose':'Remove inspected artificial flank ridges, keep original main silhouette and topology',
 'source':str(source.relative_to(HERE)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'automatic_semantic_region':False,'region_definition':{'view':[110,10],'pixel_center':[640,395],'ellipse_radii':[145,190],'view_size':[1200,900],'camera_target':[0,0,.20],'ortho_scale':.79},
 'steps':iterations,'blend':.45,'displacement_cap_m':cap,'displacement_mode':'full neighbor mean, one side only' if FULL else 'normal only','moved_vertices':int((np.linalg.norm(v-old,axis=1)>1e-7).sum()),
 'max_displacement_m':float(np.linalg.norm(v-old,axis=1).max()),'topology_changed':False,'uv_changed':False,
 'visual_pass':False,'stats':mesh_stats(cat)}
export_npz(cat,OUT/'mesh.npz');(OUT/'report.json').write_text(json.dumps(report,indent=2))
render('opposite-clay',110,10,target=(0,0,.20),scale=.79,clay=True)
render('opposite',110,10,target=(0,0,.20),scale=.79)
render('hero',-69,10,target=(0,0,.20),scale=.79)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
print('FLANK_RELAX_COMPLETE',report['moved_vertices'],report['max_displacement_m'],flush=True)
