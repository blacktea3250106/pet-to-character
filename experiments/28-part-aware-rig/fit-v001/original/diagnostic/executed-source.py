"""Actual target/scaffold/joint diagnostic renders, not generated references."""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector

P=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('fit');ap.add_argument('--case',default='original')
args=ap.parse_args(sys.argv[sys.argv.index('--')+1:]);folder=P/args.fit/args.case
d=np.load(folder/'fit.npz');r=json.loads((folder/'fit.json').read_text())
out=folder/'diagnostic';out.mkdir(exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True);sc=bpy.context.scene
sc.render.engine='CYCLES';sc.cycles.samples=16;sc.cycles.use_denoising=True
sc.render.resolution_x=640;sc.render.resolution_y=640;sc.render.resolution_percentage=100
sc.view_settings.view_transform='Standard';sc.render.image_settings.file_format='PNG'
world=bpy.data.worlds.new('DiagnosticWorld');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.8,.8,.8,1);world.node_tree.nodes['Background'].inputs[1].default_value=.7;sc.world=world
colors=[(.35,.38,.42,1),(.1,.65,.2,1),(.1,.3,.9,1),(.95,.5,.05,1),(.8,.07,.1,1),(.6,.15,.8,1),(.03,.65,.7,1)]
def mat(name,color,alpha=1):
 m=bpy.data.materials.new(name);m.diffuse_color=color;m.use_nodes=True
 nodes=m.node_tree.nodes;bs=nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=color;bs.inputs['Roughness'].default_value=.8
 if alpha<1:
  trans=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=alpha
  m.node_tree.links.new(trans.outputs[0],mix.inputs[1]);m.node_tree.links.new(bs.outputs[0],mix.inputs[2]);m.node_tree.links.new(mix.outputs[0],nodes.get('Material Output').inputs['Surface'])
 return m
mats=[mat(n,c) for n,c in zip(r['parts'],colors)];ghost=mat('Ghost',(.65,.68,.72,1),.10)
def mesh(name,v,f,labels):
 m=bpy.data.meshes.new(name);m.from_pydata(v.tolist(),[],f.tolist());m.update();ob=bpy.data.objects.new(name,m);sc.collection.objects.link(ob)
 for material in mats:m.materials.append(material)
 for i,poly in enumerate(m.polygons):poly.material_index=int(np.bincount(labels[f[i]],minlength=7).argmax())
 return ob
target=mesh('TargetParts',d['target_vertices'],d['target_triangles'],d['target_labels'])
source=mesh('WrappedScaffold',d['source_wrapped'],d['source_triangles'],d['source_labels']);source.hide_render=True
v=d['target_vertices'];lo,hi=v.min(0),v.max(0);center=Vector((lo+hi)/2);span=float(np.ptp(v,axis=0).max());diag=float(np.linalg.norm(hi-lo))
for rel,power in [((1,-1,2),100),((-1,1,1),50)]:
 ld=bpy.data.lights.new('Area','AREA');ld.energy=power;ld.size=2*span;ob=bpy.data.objects.new('Area',ld);sc.collection.objects.link(ob);ob.location=center+Vector(rel)*span;ob.rotation_euler=(center-ob.location).to_track_quat('-Z','Y').to_euler()
camdata=bpy.data.cameras.new('DiagnosticCamera');cam=bpy.data.objects.new('DiagnosticCamera',camdata);sc.collection.objects.link(cam);camdata.type='ORTHO';camdata.ortho_scale=diag*1.05;sc.camera=cam
def camera(az):
 a=math.radians(az);cam.location=center+Vector((math.cos(a),math.sin(a),.2))*3*diag;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
camera(-65)
def render(name):sc.render.filepath=str(out/(name+'.png'));bpy.ops.render.render(write_still=True)
render('target-parts');target.hide_render=True;source.hide_render=False;render('wrapped-scaffold');source.hide_render=True;target.hide_render=False
target.data.materials.clear();target.data.materials.append(ghost)
for p in target.data.polygons:p.material_index=0
for name,j in r['joints'].items():
 if name=='root' or any(s in name for s in ['tongue','eye','jaw','ear.']):continue
 color=mats[r['parts'].index(j['part'])]
 a,b=Vector(j['head']),Vector(j['tail'])
 bpy.ops.mesh.primitive_uv_sphere_add(segments=8,ring_count=4,radius=.009*span,location=a);bpy.context.object.data.materials.append(color)
 curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.bevel_depth=.0035*span;curve.bevel_resolution=1
 spline=curve.splines.new('POLY');spline.points.add(1)
 for i,pt in enumerate([a,b]):spline.points[i].co=(*pt,1)
 ob=bpy.data.objects.new(name,curve);sc.collection.objects.link(ob);curve.materials.append(color)
render('estimated-joints');camera(115);render('estimated-joints-opposite')
(out/'report.json').write_text(json.dumps({'artifact_kind':'actual_3D_diagnostic_render','palette':dict(zip(r['parts'],colors)),
 'joint_note':'Mapped heads/tails from surface fit; no claim of anatomical correctness or animation acceptance.'},indent=2)+'\n')
(out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
print('FIT_DIAGNOSTIC_COMPLETE',flush=True)
