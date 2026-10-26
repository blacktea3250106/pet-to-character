"""Bind the unchanged target using the part-aware fitted transfer scaffold."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

P=Path(__file__).resolve().parent; OLD=P.parent/'27-animation-compatibility'
ap=argparse.ArgumentParser();ap.add_argument('--case',default='original');ap.add_argument('--fit',default='fit-v002');ap.add_argument('--diagnostic-only',action='store_true');args=ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
fit=P/args.fit/args.case;out=fit/'candidate'
gate_path=fit/'fit-gate.json'
gate=json.loads(gate_path.read_text()) if gate_path.exists() else {}
if not gate.get('production_binding_allowed',False) and not args.diagnostic_only:
 raise RuntimeError('Fit acceptance missing or rejected. Only explicit --diagnostic-only may bind for failure analysis.')
out.mkdir(exist_ok=False)
(out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
r=json.loads((fit/'fit.json').read_text());d=np.load(fit/'fit.npz');inventory=json.loads((OLD/'inventory/report.json').read_text())
for key in ['source','target']:
 assert hashlib.sha256(Path(inventory[key]['path']).read_bytes()).hexdigest()==inventory[key]['sha256']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=inventory['source']['path'],use_anim=True)
src=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE');srcmesh=next(o for o in bpy.context.scene.objects if o.type=='MESH');src.data.pose_position='REST'
source_objects=set(bpy.context.scene.objects)
bpy.ops.import_scene.gltf(filepath=inventory['target']['path'])
target=next(o for o in bpy.context.scene.objects if o not in source_objects and o.type=='MESH');target.name='PersonalizedCat'
# Stress fixtures use separate copies; original case coordinates are exactly retained.
if args.case!='original':
 for i,v in enumerate(target.data.vertices):v.co=Vector(d['target_vertices'][i])
 target.data.update()
points=np.array([target.matrix_world@v.co for v in target.data.vertices]);assert np.max(np.abs(points-d['target_vertices']))<1e-6
v,f=d['source_wrapped'],d['source_triangles'];labels=d['source_labels'];names=inventory['source']['vertex_groups']
flabel=np.array([np.bincount(labels[t],minlength=7).argmax() for t in f]);trees={}
for part in range(7):
 ids=np.flatnonzero(flabel==part)
 # Near-degenerate fitted triangles cannot support stable barycentric skin transfer.
 area=np.linalg.norm(np.cross(v[f[ids,1]]-v[f[ids,0]],v[f[ids,2]]-v[f[ids,0]]),axis=1)
 ids=ids[area>1e-10]
 if not len(ids):raise ValueError('No usable source surface for part')
 trees[part]=(BVHTree.FromPolygons([Vector(p) for p in v],f[ids].tolist(),all_triangles=True),ids)
weights=np.zeros((len(points),len(names)));distances=np.zeros(len(points))
for i,point in enumerate(points):
 tree,ids=trees[int(d['target_labels'][i])];q,normal,face,distance=tree.find_nearest(Vector(point));tri=f[ids[face]]
 a,b,c=v[tri];u,w=b-a,c-a;rel=np.array(q)-a
 den=(u@u)*(w@w)-(u@w)**2
 if den<=1e-20:raise ValueError('Unstable fitted triangle')
 b1=((w@w)*(rel@u)-(u@w)*(rel@w))/den;b2=((u@u)*(rel@w)-(u@w)*(rel@u))/den
 bary=np.maximum([1-b1-b2,b1,b2],0);bary/=bary.sum()
 value=bary@d['source_weights'][tri]
 if value.sum()<=0:raise ValueError('Unweighted source')
 weights[i]=value/value.sum();distances[i]=distance
# Same fixed smoothing/influence budget as 27; comparison isolates new fit/part mapping.
target.data.calc_loop_triangles();tri=np.array([t.vertices[:] for t in target.data.loop_triangles])
span=np.ptp(points,axis=0).max();_,weld=np.unique(np.rint(points/(span*1e-7)).astype(np.int64),axis=0,return_inverse=True)
n=weld.max()+1;combined=np.zeros((n,len(names)));np.add.at(combined,weld,weights);combined/=np.bincount(weld)[:,None]
f2=weld[tri];edges=np.unique(np.sort(np.vstack([f2[:,[0,1]],f2[:,[1,2]],f2[:,[2,0]]]),axis=1),axis=0);edges=edges[edges[:,0]!=edges[:,1]];edges=np.vstack([edges,edges[:,::-1]])
degree=np.bincount(edges[:,0],minlength=n)
for _ in range(5):
 neighbor=np.zeros_like(combined);np.add.at(neighbor,edges[:,0],combined[edges[:,1]])
 combined=.65*combined+.35*neighbor/degree[:,None]
weights=combined[weld];discarded=np.zeros(len(points))
for i,value in enumerate(weights.copy()):
 keep=np.argsort(value)[-8:];discarded[i]=1-value[keep].sum();weights[i]=0;weights[i,keep]=value[keep]/value[keep].sum()

C=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
arm=bpy.data.armatures.new('PersonalizedRigData');rig=bpy.data.objects.new('PersonalizedRig',arm);bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
for bone in src.data.bones:
 j=r['joints'][bone.name];head=np.array(j['head']);tail=np.array(j['tail']);rotation=C@np.array((src.matrix_world@bone.matrix_local).to_3x3())
 eb=arm.edit_bones.new(bone.name);eb.head=Vector(head);direction=rotation[:,1]/np.linalg.norm(rotation[:,1]);eb.tail=Vector(head+direction*max(np.linalg.norm(tail-head),1e-5));eb.align_roll(Vector(rotation[:,2]));eb.use_deform=bone.use_deform;eb.use_connect=False
for bone in src.data.bones:
 if bone.parent:arm.edit_bones[bone.name].parent=arm.edit_bones[bone.parent.name]
bpy.ops.object.mode_set(mode='OBJECT')
errors=[]
for b in src.data.bones:
 arm.bones[b.name].inherit_scale=b.inherit_scale
 errors.append(np.max(np.abs(np.array(arm.bones[b.name].matrix_local.to_3x3())-C@np.array((src.matrix_world@b.matrix_local).to_3x3()))))
assert max(errors)<1e-4
for j,name in enumerate(names):
 group=target.vertex_groups.new(name=name)
 for i in np.flatnonzero(weights[:,j]>1e-8):group.add([int(i)],float(weights[i,j]),'REPLACE')
mod=target.modifiers.new('PartTransferredSkin','ARMATURE');mod.object=rig;mod.use_deform_preserve_volume=False
world=target.matrix_world.copy();target.parent=rig;target.matrix_world=world
for ob in source_objects:ob.hide_render=True;ob.hide_set(True)
rig.data.pose_position='REST';bpy.context.view_layer.update()
ev=target.evaluated_get(bpy.context.evaluated_depsgraph_get());rest=np.array([ev.matrix_world@v.co for v in ev.data.vertices]);rest_delta=float(np.max(np.abs(rest-points)))
assert rest_delta<1e-6 and len(target.data.loop_triangles)==3500
report={
 'case':args.case,'fit':str(fit),'diagnostic_only':args.diagnostic_only,'source_sha256':inventory['source']['sha256'],'target_sha256':inventory['target']['sha256'],
 'target_object':target.name,'target_rig':rig.name,'source_rig':src.name,'source_mesh':srcmesh.name,
 'canonical_rotation':C.tolist(),'scale':r['scale'],'offset':r['offset'],'bone_names':[b.name for b in arm.bones],
 'weight_groups':names,'max_influences':8,'smoothing':{'iterations':5,'factor':.35},
 'source_to_target_distance':{str(q):float(np.percentile(distances,q)) for q in [50,90,95,100]},
 'discarded_mass_after_pruning':{str(q):float(np.percentile(discarded,q)) for q in [50,95,100]},
 'rest_vertex_max_delta':rest_delta,'rest_orientation_max_abs_error':float(max(errors)),'triangles':3500,
 'animations_baked':False,'synthetic_stress_fixture':args.case!='original',
 'limitations':['Rest axes remain canonical source axes; joint heads derive from the fitted surface.',
 'No contact IK; translation tracks still use the initial affine scale.',
 'Source eye components excluded because target is a single continuous surface; independent eye control not established.'],
 'animation_pass':False,'new_cat_automation_proven':False,
}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
np.savez_compressed(out/'weights.npz',weights=weights,target_vertices=points,source_distance=distances,discarded_weight_mass=discarded)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'rigged-rest.blend'))
print(json.dumps({'case':args.case,'distance':report['source_to_target_distance'],'bones':len(arm.bones),'triangles':3500}),flush=True)
