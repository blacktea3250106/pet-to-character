"""Blender: compare generated and reduced GLBs in common coordinates, read-only.

UV correspondence is evaluated on interior samples, never inferred from UV layout.
"""
import argparse,hashlib,json,sys
from pathlib import Path
import bpy,numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('candidate',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def extract(path):
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    verts=[];triangles=[];uvs=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH':continue
        me=obj.data;me.calc_loop_triangles();offset=len(verts)
        verts += [obj.matrix_world@v.co for v in me.vertices]
        for tri in me.loop_triangles:
            triangles.append([i+offset for i in tri.vertices]);uvs.append([me.uv_layers.active.data[i].uv[:] for i in tri.loops])
    return np.array(verts),np.array(triangles),np.array(uvs)


def distances(points,tree,extent):
    values=np.array([tree.find_nearest(Vector(p))[3] for p in points])
    return {'count':len(values),'max_source_units':float(values.max()),'p95_source_units':float(np.percentile(values,95)),
            'mean_source_units':float(values.mean()),'max_extent_ratio':float(values.max()/extent),'p95_extent_ratio':float(np.percentile(values,95)/extent)}


source_v,source_t,source_uv=extract(args.source)
candidate_v,candidate_t,candidate_uv=extract(args.candidate)
extent=float(np.ptp(source_v,axis=0).max())
sc=(source_v.min(0)+source_v.max(0))/2;cc=(candidate_v.min(0)+candidate_v.max(0))/2
scale=extent/np.ptp(candidate_v,axis=0).max();aligned=(candidate_v-cc)*scale+sc
source_tree=BVHTree.FromPolygons([Vector(p) for p in source_v],source_t.tolist(),all_triangles=True)
candidate_tree=BVHTree.FromPolygons([Vector(p) for p in aligned],candidate_t.tolist(),all_triangles=True)
sampled={'source_to_candidate':distances(np.concatenate([source_v,source_v[source_t].mean(1)]),candidate_tree,extent),
         'candidate_to_source':distances(np.concatenate([aligned,aligned[candidate_t].mean(1)]),source_tree,extent)}
uv_errors=[];source_samples=[];candidate_samples=[];face_samples=[]
# Three interior samples per target triangle avoid making a vertex-seam assumption.
for weights in ((1/3,1/3,1/3),(.6,.2,.2),(.2,.6,.2)):
    for candidate_face,(xyz,uv) in enumerate(zip(np.einsum('tvc,v->tc',aligned[candidate_t],weights),np.einsum('tvc,v->tc',candidate_uv,weights))):
        point,_,face,_=source_tree.find_nearest(Vector(xyz));tri=source_v[source_t[face]]
        ab=tri[1]-tri[0];ac=tri[2]-tri[0];ap=np.array(point)-tri[0]
        gram=np.array([[ab@ab,ab@ac],[ab@ac,ac@ac]])
        if abs(np.linalg.det(gram))<1e-18:continue
        b,c=np.linalg.solve(gram,np.array([ap@ab,ap@ac]));source_sample=np.array([1-b-c,b,c])@source_uv[face]
        uv_errors.append(float(np.linalg.norm(source_sample-uv)))
        source_samples.append(source_sample);candidate_samples.append(uv);face_samples.append(candidate_face)
errors=np.array(uv_errors)
report={'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
        'source_triangles':len(source_t),'candidate_triangles':len(candidate_t),
        'source_bounds':[source_v.min(0).tolist(),source_v.max(0).tolist()],
        'candidate_bounds':[candidate_v.min(0).tolist(),candidate_v.max(0).tolist()],
        'uniform_alignment':{'scale':float(scale),'source_center':sc.tolist(),'candidate_center':cc.tolist(),'rotation_applied':False,'per_axis_deformation':False},
        'sampled_surface_distance':sampled,'distance_scope':'World-space vertices and triangle centroids after uniform bbox alignment; source GLB units are not true pet measurements; not continuous Hausdorff distance or anatomical proof',
        'uv_surface_correspondence':{'samples':len(errors),'p50':float(np.percentile(errors,50)),'p95':float(np.percentile(errors,95)),'max':float(errors.max()),'fraction_within_one_2048_texel':float(np.mean(errors<=1/2048)),'scope':'Nearest-source-surface interpolation at three interior samples per target triangle; UV chart ambiguity may occur near seams. Not a whole-surface identity score.'},
        'source_extent':extent,'geometry_review_trigger_pass':all(d['max_extent_ratio']<.01 and d['p95_extent_ratio']<.003 for d in sampled.values()),'asset_accepted':False}
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2))
np.savez_compressed(args.output.with_suffix('.samples.npz'),source_uv=np.array(source_samples),candidate_uv=np.array(candidate_samples),candidate_face=np.array(face_samples),source_sha256=report['source_sha256'],candidate_sha256=report['candidate_sha256'])
args.output.with_suffix('.executed.py').write_bytes(Path(__file__).read_bytes())
print('SURFACE_COMPARISON',json.dumps(report),flush=True)
