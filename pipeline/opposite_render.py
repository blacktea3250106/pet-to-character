"""Render/export the isolated opposite-side color candidate in background Blender."""
import argparse, ast, hashlib, json, math, sys
from pathlib import Path
import bpy, bmesh, numpy as np
from mathutils import Vector

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--profile',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
cfg=json.loads(args.profile.read_text()) if args.profile else {}
OUT=HERE/cfg.get('output','11-other-side/color-v001');OUT.mkdir(exist_ok=True)
executed_source=Path(__file__).read_bytes();(OUT/'executed-source.py').write_bytes(executed_source)
source=HERE/cfg.get('scene','10-style-recovery/eye-material/scene.blend')
texture=HERE/cfg.get('texture','11-other-side/projection-v002/color.png')
assert texture.is_file()
tree=ast.parse((HERE/'blender_stage.py').read_text())
helpers={'bsdf','make_mat','render','export_npz','mesh_stats'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in helpers],type_ignores=[]),'render_helpers','exec'))
bpy.ops.wm.open_mainfile(filepath=str(source))
cat=bpy.data.objects['Cat'];nt=cat.data.materials[0].node_tree
node=nt.nodes.new('ShaderNodeTexImage');node.image=bpy.data.images.load(str(texture),check_existing=False)
nt.links.new(node.outputs['Color'],bsdf(cat.data.materials[0]).inputs['Base Color'])
sc=bpy.context.scene;sc.cycles.samples=32
views=cfg.get('views',[('opposite',110,10,(0,0,.20),.79),('hero',-69,10,(0,0,.20),.79),('back-high',110,48,(0,0,.20),.79)])
for name,az,el,target,scale in views:render(name,az,el,target=target,scale=scale)
# Verify CPU projection uses Blender's actual render camera convention.
_,az,el,target,scale=views[0];a,e=map(math.radians,[az,el]);cam=sc.camera
direction=Vector((math.cos(a)*math.cos(e),math.sin(a)*math.cos(e),math.sin(e)))
cam.location=Vector(target)+direction*2
cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
bpy.context.view_layer.update()
points=np.array([cat.matrix_world@v.co for v in cat.data.vertices])
right=np.array([-math.sin(a),math.cos(a),0]);up=np.cross(np.array(direction),right)
W,H=sc.render.resolution_x,sc.render.resolution_y
cpu=np.column_stack([W/2+(points-np.array(target))@right*W/scale,H/2-(points-np.array(target))@up*W/scale])
projection=cam.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=W,y=H,scale_x=sc.render.pixel_aspect_x,scale_y=sc.render.pixel_aspect_y)
matrix=np.array(projection@cam.matrix_world.inverted())
clip=np.column_stack([points,np.ones(len(points))])@matrix.T
ndc=clip[:,:3]/clip[:,3,None]
actual=np.column_stack([(ndc[:,0]+1)*W/2,(1-ndc[:,1])*H/2])
projection_error=float(np.linalg.norm(actual-cpu,axis=1).max());assert projection_error<.01,projection_error
export_npz(cat,OUT/'mesh.npz')
before=np.load(source.parent/'mesh.npz');after=np.load(OUT/'mesh.npz')
unchanged={key:bool(np.array_equal(before[key],after[key])) for key in ['verts','tris','tri_uv','material_ids']}
assert all(unchanged.values())
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);bpy.context.view_layer.objects.active=cat
bpy.ops.export_scene.gltf(filepath=str(OUT/'cat.glb'),export_format='GLB',use_selection=True)
report={'source':str(source.relative_to(HERE)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'texture':str(texture.relative_to(HERE)),'texture_sha256':hashlib.sha256(texture.read_bytes()).hexdigest(),'profile':cfg,'script_sha256':hashlib.sha256(executed_source).hexdigest(),'unchanged_arrays':unchanged,'projection_max_error_px':projection_error,'stats':mesh_stats(cat),'views':views,'identity_or_art_pass':False,'animation_compatibility':'not_tested','adopted_as_selected_asset':False,'manual_review_pending':True}
(OUT/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('OPPOSITE_RENDER_COMPLETE',json.dumps(unchanged),flush=True)
