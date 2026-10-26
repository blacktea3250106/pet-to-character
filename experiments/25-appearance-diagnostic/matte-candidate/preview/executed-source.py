"""Background Blender review with generic bbox framing; source GLB is read-only."""
import argparse, hashlib, json, math, sys
from pathlib import Path
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector

parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
parser.add_argument('--views',type=int,nargs='+',default=[-45,0,45,90,135,180,225,270])
parser.add_argument('--skip-diagnostics',action='store_true')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
source=args.source.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:raise RuntimeError('No mesh instances')
pts=np.array([o.matrix_world@v.co for o in meshes for v in o.data.vertices])
lo,hi=pts.min(0),pts.max(0);span=float(max(hi-lo));scale=.65/span
origin=Vector(((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]))
transform=Matrix.Scale(scale,4)@Matrix.Translation(-origin)
for ob in list(bpy.context.scene.objects):
    if ob.parent is None:ob.matrix_world=transform@ob.matrix_world
bpy.context.view_layer.update()
pts=np.array([o.matrix_world@v.co for o in meshes for v in o.data.vertices])
mn,mx=pts.min(0),pts.max(0);center=Vector((mn+mx)/2);diagonal=float(np.linalg.norm(mx-mn))
report={'artifact_kind':'actual_3D_render','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_bounds':[lo.tolist(),hi.tolist()],'review_bounds':[mn.tolist(),mx.tolist()],
        'normalization':{'scale':scale,'source_origin':list(origin),'scope':'Uniform scale and translation on review scene only; no rotation, mesh edits or true pet size claim'},
        'camera_semantics':'Azimuth in imported Blender world axes; anatomical labels not inferred automatically',
        'blender':bpy.app.version_string,'geometry':[],'materials':[],'renders':[],'asset_accepted':False}
combined=bmesh.new()
for ob in meshes:
    me=ob.data;me.calc_loop_triangles()
    report['geometry'].append({'name':ob.name,'vertices':len(me.vertices),'triangles':len(me.loop_triangles),'polygons':len(me.polygons),
                               'uv_layers':len(me.uv_layers),'smooth_polygons':sum(p.use_smooth for p in me.polygons)})
    # Analysis copy uses world positions; original vertices, UVs and normals stay untouched.
    verts=[combined.verts.new(ob.matrix_world@v.co) for v in me.vertices]
    for tri in me.loop_triangles:combined.faces.new([verts[i] for i in tri.vertices])
bmesh.ops.remove_doubles(combined,verts=list(combined.verts),dist=.65e-6)
report['analysis_weld_tolerance_m']=.65e-6
report['analysis_topology']={'vertices':len(combined.verts),'boundary_edges':sum(e.is_boundary for e in combined.edges),
                            'nonmanifold_edges':sum(not e.is_manifold for e in combined.edges),'meaning':'Analysis-copy topology; not anatomical or animation acceptance'}
combined.free()
for mat in list(bpy.data.materials):
    item={'name':mat.name,'use_nodes':mat.use_nodes,'images':[]}
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type=='BSDF_PRINCIPLED':
                for label in ('Metallic','Roughness','Specular IOR Level'):
                    if label in node.inputs:item[label]={'value':node.inputs[label].default_value,'linked':node.inputs[label].is_linked}
            if node.type=='TEX_IMAGE' and node.image:
                im=node.image;item['images'].append({'name':im.name,'size':list(im.size),'color_space':im.colorspace_settings.name})
    report['materials'].append(item)
sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=24;sc.cycles.use_denoising=True
sc.render.resolution_x=1024;sc.render.resolution_y=1024;sc.render.resolution_percentage=100
sc.render.image_settings.file_format='PNG';sc.render.film_transparent=False
sc.view_settings.view_transform='Standard';sc.view_settings.exposure=0;sc.view_settings.gamma=1
world=bpy.data.worlds.new('NeutralReviewWorld');world.use_nodes=True;sc.world=world
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.72,.72,.72,1);bg.inputs['Strength'].default_value=.25
def plain(name,color):
    mat=bpy.data.materials.new(name);mat.use_nodes=True;node=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    node.inputs['Base Color'].default_value=(*color,1);node.inputs['Roughness'].default_value=.9;node.inputs['Metallic'].default_value=0
    return mat
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,float(mn[2])-.002));ground=bpy.context.object;ground.name='ReviewGround';ground.data.materials.append(plain('Ground',(.65,.65,.65)))
for name,loc,power,size in [('Key',(.6,-.8,1.1),15,.8),('Fill',(.3,.7,.7),8,1),('Rim',(-.7,.1,1),10,.7)]:
    light=bpy.data.lights.new(name,'AREA');light.energy=power;light.shape='DISK';light.size=size
    ob=bpy.data.objects.new(name,light);sc.collection.objects.link(ob);ob.location=loc;ob.rotation_euler=(center-ob.location).to_track_quat('-Z','Y').to_euler()
data=bpy.data.cameras.new('ReviewCamera');cam=bpy.data.objects.new('ReviewCamera',data);sc.collection.objects.link(cam);sc.camera=cam;data.type='ORTHO';data.ortho_scale=diagonal*1.08
clay=plain('DiagnosticClay',(.55,.55,.55))
def render(az,el,mode):
    a,e=math.radians(az),math.radians(el)
    cam.location=center+Vector((math.cos(a)*math.cos(e),math.sin(a)*math.cos(e),math.sin(e)))*max(diagonal*3,2)
    cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
    name=f'{mode}-az{az%360:03d}-el{el:02d}.png'
    sc.view_layers[0].material_override=clay if mode=='clay' else None
    sc.render.filepath=str(out/name);bpy.ops.render.render(write_still=True)
    report['renders'].append({'file':name,'mode':mode,'azimuth_degrees':az,'elevation_degrees':el,'target':list(center),'ortho_scale':data.ortho_scale})
for az in args.views:render(az,12,'original')
if not args.skip_diagnostics:
    for az in (-45,45,135,225):render(az,12,'clay')
    render(45,60,'original')
sc.view_layers[0].material_override=None
# Save the unedited imported surface before the isolated flat-shading comparison.
bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'))
smooth={o.name:[p.use_smooth for p in o.data.polygons] for o in meshes}
for ob in meshes:
    for poly in ob.data.polygons:poly.use_smooth=False
if not args.skip_diagnostics:
    for az in (-45,45):render(az,12,'flat-only')
for ob in meshes:
    for poly,flag in zip(ob.data.polygons,smooth[ob.name]):poly.use_smooth=flag
report['triangle_count']=sum(item['triangles'] for item in report['geometry'])
report['flat_only_scope']='Not run; source asset rendered as imported' if args.skip_diagnostics else 'Diagnostic shading flag only; no topology, color, material or geometry edits; saved scene retains source normals/shading'
(out/'report.json').write_text(json.dumps(report,indent=2))
(out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
print('REVIEW_COMPLETE',json.dumps({'triangles':report['triangle_count'],'renders':len(report['renders']),'topology':report['analysis_topology']}),flush=True)
