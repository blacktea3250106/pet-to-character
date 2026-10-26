from pathlib import Path
import bpy, json, tarfile, hashlib
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
(OUT/'source').mkdir(parents=True,exist_ok=True)
(OUT/'preview').mkdir(exist_ok=True)
with tarfile.open(ROOT/'Low Poly Animated Cats.unitypackage','r:gz') as archive:
    for item in archive.getmembers():
        if not item.isfile() or not item.name.endswith('/pathname'): continue
        path=archive.extractfile(item).read().decode('utf-8',errors='replace').split('\n')[0].rstrip('\x00')
        if 'Cat_Domestic_Shorthair' in path and path.lower().endswith(('.fbx','.png','.mat')) and '/Icon' not in path:
            asset=archive.extractfile(item.name.rsplit('/',1)[0]+'/asset')
            (OUT/'source'/Path(path).name).write_bytes(asset.read())
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(OUT/'source/SKM_Cat_Domestic_Shorthair.fbx'),use_anim=True)
mesh=next(o for o in bpy.data.objects if o.type=='MESH')
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
rig.animation_data_clear()
rig.data.pose_position='REST'
mesh.data.calc_loop_triangles()
data={'mesh_name':mesh.name,'matrix':list(map(list,mesh.matrix_world)),
      'vertices':[list(v.co) for v in mesh.data.vertices],
      'normals':[list(v.normal) for v in mesh.data.vertices],
      'triangles':[list(t.vertices) for t in mesh.data.loop_triangles],
      'uv':[[list(mesh.data.uv_layers[0].data[i].uv) for i in t.loops] for t in mesh.data.loop_triangles],
      'groups':{g.index:g.name for g in mesh.vertex_groups},
      'weights':[{str(g.group):g.weight for g in v.groups} for v in mesh.data.vertices],
      'bones':{b.name:{'head':list(b.head_local),'tail':list(b.tail_local)} for b in rig.data.bones},
      'actions':[a.name for a in bpy.data.actions],
      'dimensions':list(mesh.dimensions), 'uv_layers':[u.name for u in mesh.data.uv_layers]}
(OUT/'mesh-info.json').write_text(json.dumps(data))
mat=mesh.data.materials[0];mat.use_nodes=True
nt=mat.node_tree;nt.nodes.clear()
out=nt.nodes.new('ShaderNodeOutputMaterial');bs=nt.nodes.new('ShaderNodeBsdfPrincipled')
tex=nt.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(OUT/'source/Cat_Domestic_Shorthair_COL_2k.png'))
nt.links.new(tex.outputs['Color'],bs.inputs['Base Color']);nt.links.new(bs.outputs['BSDF'],out.inputs['Surface'])
bs.inputs['Roughness'].default_value=0.82
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24
scene.cycles.use_denoising=True
scene.world=bpy.data.worlds.new('Neutral studio');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(0.35,0.35,0.35,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value=0.45
points=[mesh.matrix_world@v.co for v in mesh.data.vertices]
lo=Vector(tuple(min(p[i] for p in points) for i in range(3)));hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
center=(lo+hi)*0.5;span=max(hi-lo)
bpy.ops.mesh.primitive_plane_add(size=span*200,location=(0,0,lo.z-0.005))
floor=bpy.context.object;floor.name='StudioFloor'
fm=bpy.data.materials.new('Warm grey ground');fm.diffuse_color=(0.18,0.2,0.22,1);floor.data.materials.append(fm)
for name,relative,power,size in [('Key',(2,-3,4),650,3),('Fill',(-3,-1,2),350,4),('Rim',(0,3,4),550,3)]:
    ld=bpy.data.lights.new(name,'AREA');ld.energy=power*span*span;ld.shape='DISK';ld.size=size*span
    ob=bpy.data.objects.new(name,ld);scene.collection.objects.link(ob);ob.location=center+Vector(relative)*span
    ob.rotation_euler=(center-ob.location).to_track_quat('-Z','Y').to_euler()
camd=bpy.data.cameras.new('PreviewCamera');cam=bpy.data.objects.new('PreviewCamera',camd);scene.collection.objects.link(cam)
scene.camera=cam;camd.type='ORTHO';camd.ortho_scale=span*1.4
cam.location=center+Vector((2,-3,1.5))*span;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(OUT/'preview/original-inspection.png')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'original-preview.blend'))
bpy.ops.render.render(write_still=True)
print(json.dumps({'vertices':len(mesh.data.vertices),'triangles':len(mesh.data.loop_triangles),'bounds':[list(lo),list(hi)],'bones':data['bones'],'actions':data['actions']},indent=2))
