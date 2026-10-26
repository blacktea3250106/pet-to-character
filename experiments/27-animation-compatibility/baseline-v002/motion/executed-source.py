"""Actual skinned Blender animation renders; no generated reference imagery."""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector

P=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('candidate');ap.add_argument('--motion',action='store_true')
args=ap.parse_args(sys.argv[sys.argv.index('--')+1:])
folder=P/args.candidate; out=folder/('motion' if args.motion else 'preview')
if out.exists():raise RuntimeError('Preserve existing renders')
out.mkdir()
r=json.loads((folder/'report.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(folder/'animated.blend'))
cat=bpy.data.objects[r['target_object']];rig=bpy.data.objects[r['target_rig']]
rest=np.array([cat.matrix_world@v.co for v in cat.data.vertices]);lo,hi=rest.min(0),rest.max(0)
center=Vector((lo+hi)/2);span=float(np.ptp(rest,axis=0).max());diag=float(np.linalg.norm(hi-lo))
sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=12;sc.cycles.seed=0;sc.cycles.use_denoising=True
sc.render.resolution_x=640 if not args.motion else 512;sc.render.resolution_y=sc.render.resolution_x;sc.render.resolution_percentage=100
sc.render.image_settings.file_format='PNG';sc.view_settings.view_transform='Standard';sc.view_settings.exposure=0;sc.view_settings.gamma=1
world=bpy.data.worlds.new('MotionReviewWorld');world.use_nodes=True;sc.world=world
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.72,.72,.72,1);bg.inputs['Strength'].default_value=.25
mat=bpy.data.materials.new('ReviewFloor');mat.use_nodes=True
bsdf=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bsdf.inputs['Base Color'].default_value=(.65,.65,.65,1);bsdf.inputs['Roughness'].default_value=.9
bpy.ops.mesh.primitive_plane_add(size=200*span,location=(0,0,float(lo[2])-.002*span));bpy.context.object.data.materials.append(mat)
for name,rel,power,size in [('Key',(.6,-.8,1.1),15,.8),('Fill',(.3,.7,.7),8,1),('Rim',(-.7,.1,1),10,.7)]:
 light=bpy.data.lights.new(name,'AREA');light.energy=power*(span/.65)**2;light.shape='DISK';light.size=size*(span/.65)
 ob=bpy.data.objects.new(name,light);sc.collection.objects.link(ob);ob.location=Vector((lo[0]+hi[0],lo[1]+hi[1],2*lo[2]))/2+Vector(rel)*(span/.65);ob.rotation_euler=(center-ob.location).to_track_quat('-Z','Y').to_euler()
data=bpy.data.cameras.new('MotionCamera');cam=bpy.data.objects.new('MotionCamera',data);sc.collection.objects.link(cam);sc.camera=cam;data.type='ORTHO';data.ortho_scale=diag*1.13
a,e=math.radians(-45),math.radians(14);cam.location=center+Vector((math.cos(a)*math.cos(e),math.sin(a)*math.cos(e),math.sin(e)))*diag*3;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
if args.motion:
 plans={'Walk':list(range(1,28,2)),'Idle_to_Sit':list(range(1,36,2)),'Sitting_to_Idle':list(range(1,36,2))}
else:
 plans={'Idle':[1],'Walk':[7,20],'Idle_to_Sit':[18,35],'Sitting':[1],'Sitting_to_Idle':[18,35]}
records=[]
for name,frames in plans.items():
 action=bpy.data.actions[name];rig.animation_data.action=action;rig.animation_data.action_slot=action.slots[0]
 for frame in frames:
  sc.frame_set(frame);sc.render.filepath=str(out/f'{name}-{frame:04d}.png');bpy.ops.render.render(write_still=True)
  records.append({'action':name,'frame':frame,'file':f'{name}-{frame:04d}.png'})
(out/'report.json').write_text(json.dumps({'artifact_kind':'actual_skinned_3D_animation_render','candidate':args.candidate,'renders':records,'fps_source':30,'frame_step':2 if args.motion else None,'camera':{'center':list(center),'ortho_scale':data.ortho_scale},'note':'In-place source animation; no foot IK or locomotion root travel imposed.'},indent=2)+'\n')
(out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
print('MOTION_RENDER_COMPLETE',len(records),flush=True)
