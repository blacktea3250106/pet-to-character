"""Apply the imagegen low-poly atlas to the unchanged asset for visual QA."""
from pathlib import Path
import bpy, json, hashlib
from mathutils import Vector
P=Path(__file__).resolve().parent
bpy.ops.wm.open_mainfile(filepath=str(P/'semantic-skin-test.blend'))
cat=bpy.data.objects['SKM_Cat_Domestic_Shorthair'];mesh=cat.data
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
mesh.calc_loop_triangles()
def digest():
    d={'vertices':[list(v.co) for v in mesh.vertices],'faces':[list(p.vertices) for p in mesh.polygons],
       'uv':[[list(d.uv) for d in u.data] for u in mesh.uv_layers],
       'weights':[[[g.group,g.weight] for g in v.groups] for v in mesh.vertices],
       'bones':[[b.name,list(b.head_local),list(b.tail_local)] for b in rig.data.bones]}
    return hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
im=bpy.data.images.load(str(P/'textures/Cat_LowPoly_Generated.png'));im.colorspace_settings.name='sRGB';im.pack()
node=next(n for n in cat.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE');node.image=im
scene=bpy.context.scene
for ob in bpy.data.objects:
    if ob.type=='LIGHT':ob.data.energy*=.28
scene.world.node_tree.nodes['Background'].inputs[1].default_value=.20
scene.render.resolution_x=1400;scene.render.resolution_y=1050;scene.cycles.samples=32
cam=scene.camera;cam.data.ortho_scale=.68
points=[cat.matrix_world@v.co for v in mesh.vertices]
lo=Vector(tuple(min(p[i] for p in points) for i in range(3)));hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
center=(lo+hi)*.5;center.y-=.035;span=max(hi-lo)
def view(d):
    cam.location=center+Vector(d)*span;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
view((-2,-3,1.35))
for a in bpy.data.actions:a.use_fake_user=True
v=json.loads((P/'validation.json').read_text());assert digest()==v['original_geometry_uv_rig_sha256']
v.update({'result_geometry_uv_rig_sha256':digest(),'generated_texture_size':list(im.size),
          'image_generation_mode':'built-in imagegen',
          'image_generation_prompt':'imagegen-prompt.txt',
          'final_stage':'AI refinement of semantic UV color regions; local render inspection required',
          'glb_purpose':'Static visual preview without animations; blend retains all original actions and weights.',
          'glb_limit':'glTF preview keeps top 4 skin weights; do not use as master animation asset.'})
(P/'validation.json').write_text(json.dumps(v,ensure_ascii=False,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(P/'lowpoly-skin-test.blend'))
for name,d in [('front-right',(-2,-3,1.35)),('front-left',(2,-3,1.35)),('right',(-3,0,.8)),('back-top',(1.8,2.5,3.5))]:
    view(d);scene.render.filepath=str(P/'preview'/('lowpoly-'+name+'.png'));bpy.ops.render.render(write_still=True)
view((-2,-3,1.35))
bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=cat
bpy.ops.export_scene.gltf(filepath=str(P/'lowpoly-skin-test.glb'),export_format='GLB',use_selection=True,export_animations=False,export_yup=True)
print('FINAL GEOMETRY MATCH',digest(),flush=True)
