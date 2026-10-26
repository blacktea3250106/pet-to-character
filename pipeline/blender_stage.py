"""Run only in an isolated background Blender, never in the user's live scene."""
import bpy,bmesh,json,math,sys
from pathlib import Path
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE=Path(__file__).resolve().parent
stage=sys.argv[sys.argv.index('--')+1] if '--' in sys.argv else 'raw'
SINGLE='--single' in sys.argv
RAWDIR='06c-raw-single' if SINGLE else '06-raw-model'
GEODIR='07b-geometry' if SINGLE else '07-geometry'
COLORDIR='08b-coat' if SINGLE else '08-coat'
FINALDIR='09b-material' if SINGLE else '09-material'
TRIPODIR='05b-tripo' if SINGLE else '05-tripo'
OUT=HERE/({'raw':RAWDIR,'repair':'06b-repair','geometry':GEODIR,'color':COLORDIR,'final':FINALDIR}[stage]);OUT.mkdir(exist_ok=True)

def bsdf(mat):return next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
def make_mat(name,color,rough=.9):
 m=bpy.data.materials.new(name);m.use_nodes=True;p=bsdf(m);p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=0;return m

def setup():
 sc=bpy.context.scene
 try:sc.render.engine='CYCLES'
 except TypeError:pass
 sc.cycles.samples=24;sc.cycles.use_denoising=True
 sc.render.resolution_x=800;sc.render.resolution_y=800;sc.render.resolution_percentage=100
 sc.render.image_settings.file_format='PNG';sc.render.film_transparent=False
 try:sc.view_settings.view_transform='Standard'
 except TypeError:pass
 sc.view_settings.exposure=0;sc.view_settings.gamma=1
 world=bpy.data.worlds.new('ReviewWorld');world.use_nodes=True;sc.world=world
 bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs['Color'].default_value=(.72,.72,.72,1);bg.inputs['Strength'].default_value=.25
 bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.002));ground=bpy.context.object;ground.name='ReviewGround';ground.data.materials.append(make_mat('Ground',(.65,.65,.65),1))
 for name,loc,power,size in [('Key',(.6,-.8,1.1),15,.8),('Fill',(.3,.7,.7),8,1),('Rim',(-.7,.1,1.0),10,.7)]:
  data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
  ob=bpy.data.objects.new(name,data);sc.collection.objects.link(ob);ob.location=loc;ob.rotation_euler=(Vector((0,0,.2))-ob.location).to_track_quat('-Z','Y').to_euler()
 data=bpy.data.cameras.new('ReviewCamera');cam=bpy.data.objects.new('ReviewCamera',data);sc.collection.objects.link(cam);sc.camera=cam;data.type='ORTHO';data.ortho_scale=.84

def render(name,az,el,target=(0,0,.24),scale=.84,clay=False,unlit=False):
 sc=bpy.context.scene;cam=sc.camera;a,e=math.radians(az),math.radians(el)
 cam.location=Vector(target)+Vector((math.cos(a)*math.cos(e),math.sin(a)*math.cos(e),math.sin(e)))*2
 cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale
 sc.view_layers[0].material_override=make_mat('Clay',(.55,.55,.55)) if clay else None
 sc.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
 sc.view_layers[0].material_override=None

def export_npz(obj,path):
 me=obj.data;me.calc_loop_triangles()
 verts=np.array([obj.matrix_world@v.co for v in me.vertices],np.float32)
 tris=np.array([t.vertices[:] for t in me.loop_triangles],np.int32)
 uv=me.uv_layers.active
 tri_uv=np.array([[uv.data[i].uv[:] for i in t.loops] for t in me.loop_triangles],np.float32)
 mids=np.array([t.material_index for t in me.loop_triangles],np.int32)
 np.savez(path,verts=verts,tris=tris,tri_uv=tri_uv,material_ids=mids)

def mesh_stats(cat):
 cat.data.calc_loop_triangles()
 bm=bmesh.new();bm.from_mesh(cat.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=6.5e-7)
 r={'vertices':len(cat.data.vertices),'polygons':len(cat.data.polygons),'triangles':len(cat.data.loop_triangles),'triangle_count_method':'evaluated mesh loop triangles, not polygon count','welded_vertices':len(bm.verts),'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),'low_height_components':[]}
 for height in [.05,.08,.11]:
  remaining={v for v in bm.verts if v.co.z<height};groups=[]
  while remaining:
   v=remaining.pop();stack=[v];group=[v]
   while stack:
    v=stack.pop()
    for e in v.link_edges:
     other=e.other_vert(v)
     if other in remaining:remaining.remove(other);stack.append(other);group.append(other)
   if len(group)>4:groups.append({'n':len(group),'center':np.mean([v.co[:] for v in group],0).tolist()})
  r['low_height_components'].append({'height':height,'count':len(groups),'groups':groups})
 bm.free();return r

def save_stage(cat,report):
 export_npz(cat,OUT/'mesh.npz');report.update(mesh_stats(cat))
 report['view_transform']=bpy.context.scene.view_settings.view_transform
 (OUT/'report.json').write_text(json.dumps(report,indent=2))
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
 bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);bpy.context.view_layer.objects.active=cat
 bpy.ops.export_scene.gltf(filepath=str(OUT/'cat.glb'),export_format='GLB',use_selection=True)

if stage=='raw':
 bpy.ops.wm.read_factory_settings(use_empty=True)
 state=json.loads((HERE/TRIPODIR/'state.json').read_text())
 candidates=[d['file'] for d in state['downloads'] if d['file'].endswith('.glb')]
 if not candidates:raise RuntimeError('No downloaded GLB')
 preferred=next((p for p in candidates if p in ['model_url.glb','model.glb','pbr_model.glb']),candidates[0])
 bpy.ops.import_scene.gltf(filepath=str(HERE/TRIPODIR/preferred))
 objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
 points=np.array([o.matrix_world@v.co for o in objs for v in o.data.vertices]);lo=points.min(0);hi=points.max(0)
 scale=float(.65/max(hi-lo));offset=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
 for o in objs:
  for v in o.data.vertices:v.co=Vector((np.array(o.matrix_world@v.co)-offset)*scale)
  o.matrix_world.identity()
 bpy.ops.object.select_all(action='DESELECT')
 for o in objs:o.select_set(True)
 bpy.context.view_layer.objects.active=objs[0];bpy.ops.object.join();cat=bpy.context.object;cat.name='Cat'
 orientation_note=None
 if SINGLE:
  # Reviewed principal axis of the four foot centers in the first import.
  theta=math.radians(-69.72070751701202)
  rot=np.array([[math.cos(theta),-math.sin(theta),0],[math.sin(theta),math.cos(theta),0],[0,0,1]])
  vv=np.array([v.co[:] for v in cat.data.vertices])@rot.T
  mn,mx=vv.min(0),vv.max(0);factor=.65/max(mx-mn)
  center=np.array([(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,mn[2]])
  for vertex,point in zip(cat.data.vertices,vv):vertex.co=Vector((point-center)*factor)
  orientation_note={'body_axis_rotation_degrees':-69.72070751701202,'method':'reviewed four-foot-center PCA axis; forward sign verified on face','additional_scale':float(factor),'head_turn':'generated head yaw is retained; not an animation-ready neutral rest pose claim'}
 # No geometry edits: normalize coordinates only; keep raw materials and normals.
 setup()
 report={'stage':'raw','source':preferred,'source_bounds':[lo.tolist(),hi.tolist()],'normalization':'longest bbox extent 0.65 m, centered XY, floor Z=0; not measured pet size','scale':scale,'vertices':len(cat.data.vertices),'triangles':len(cat.data.polygons),'materials':len(cat.data.materials),'blender':bpy.app.version_string}
 report['orientation']=orientation_note
 for i,mat in enumerate(cat.data.materials):
  for node in mat.node_tree.nodes:
   if node.type=='TEX_IMAGE' and node.image:
    image=node.image;image.filepath_raw=str(OUT/f'material-{i}-{image.name.replace("/","_")}.png');image.file_format='PNG';image.save()
 report['image_files']=[p.name for p in OUT.glob('material-*.png')]
 export_npz(cat,OUT/'mesh.npz')
 bm=bmesh.new();bm.from_mesh(cat.data);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=6.5e-7)
 report['analysis_welded_vertices']=len(bm.verts);report['boundary_edges']=sum(e.is_boundary for e in bm.edges);report['nonmanifold_edges']=sum(not e.is_manifold for e in bm.edges)
 report['low_height_components']=[]
 height=max(v.co.z for v in bm.verts)
 for ratio in [.10,.16,.22]:
  remaining={v for v in bm.verts if v.co.z<height*ratio};groups=[]
  while remaining:
   seed=remaining.pop();stack=[seed];part=[seed]
   while stack:
    v=stack.pop()
    for e in v.link_edges:
     other=e.other_vert(v)
     if other in remaining:remaining.remove(other);stack.append(other);part.append(other)
   if len(part)>4:groups.append({'vertices':len(part),'centroid':np.mean([v.co[:] for v in part],axis=0).tolist()})
  report['low_height_components'].append({'height':ratio*height,'count':len(groups),'groups':groups,'meaning':'geometric candidate components, not automatic anatomical proof'})
 bm.free()
 (OUT/'report.json').write_text(json.dumps(report,indent=2))
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
elif stage=='repair':
 bpy.ops.wm.open_mainfile(filepath=str(HERE/'06-raw-model/scene.blend'));cat=bpy.data.objects['Cat']
 bm=bmesh.new();bm.from_mesh(cat.data)
 bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=6.5e-7)
 bm.verts.ensure_lookup_table();bm.verts.index_update()
 mirrored=[(v.co.x,.07-v.co.y,v.co.z) for v in bm.verts]
 goodhalf=[tuple(v.index for v in f.verts) for f in bm.faces if all(v.co.y<.042 for v in f.verts)]
 support=BVHTree.FromPolygons(mirrored,goodhalf,all_triangles=True)
 # Case-specific, visually verified extra appendage; do not reuse as an automatic rule.
 doomed=[v for v in bm.verts if -.175<v.co.x<-.045 and .025<v.co.y<.115 and v.co.z<.175]
 removed=len(doomed);bmesh.ops.delete(bm,geom=doomed,context='VERTS')
 border=[e for e in bm.edges if e.is_boundary]
 filled=bmesh.ops.holes_fill(bm,edges=border,sides=0)['faces']
 patch=make_mat('InferredRepairFur',(.018,.012,.009),.9);cat.data.materials.append(patch)
 for f in filled:f.material_index=len(cat.data.materials)-1
 bmesh.ops.triangulate(bm,faces=list(filled))
 # Replace the flat cap by a locally fitted surface from the intact opposite flank.
 # Only geometry uses this symmetry; original asymmetric coat is retained elsewhere.
 patchfaces=[f for f in bm.faces if f.material_index==len(cat.data.materials)-1]
 pe=list({e for f in patchfaces for e in f.edges})
 bmesh.ops.subdivide_edges(bm,edges=pe,cuts=2,use_grid_fill=True)
 patchverts={v for f in bm.faces if f.material_index==len(cat.data.materials)-1 for v in f.verts}
 for v in patchverts:
  hit=support.find_nearest(v.co)
  if hit[0] is not None:v.co=hit[0]
 bmesh.ops.triangulate(bm,faces=list(bm.faces))
 bmesh.ops.remove_doubles(bm,verts=list(patchverts),dist=0.00003)
 bmesh.ops.dissolve_degenerate(bm,dist=1e-7,edges=list(bm.edges))
 bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
 bm.to_mesh(cat.data);bm.free();cat.data.update()
 report={'stage':'local structural repair v2','automatic_repair':False,'removed_vertices':removed,'filled_boundary_edges':len(border),'method':'delete duplicate hindlimb branch; subdivide opening patch and locally fit to mirrored intact opposite flank geometry; no compressed hidden limb','geometry_inference':'local opposite-flank symmetry only for repair patch; not measured pet shape','patch_color':'temporary inferred dark fur; independent material, to reproject separately','selection_bounds':{'x':[-.175,-.045],'y':[.025,.115],'z_max':.175}}
 save_stage(cat,report)
elif stage=='geometry':
 bpy.ops.wm.open_mainfile(filepath=str(HERE/(RAWDIR if SINGLE else '06b-repair')/'scene.blend'));cat=bpy.data.objects['Cat']
 bm=bmesh.new();bm.from_mesh(cat.data)
 # Working-copy positions are shared before smoothing; per-face-corner UVs remain distinct.
 # Otherwise independently smoothing imported UV-split vertices opens visible cracks.
 bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=6.5e-7)
 # One midpoint subdivision; smooth only body midsurface, preserve face, ears and paws.
 bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=1,use_grid_fill=True)
 bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.verts.ensure_lookup_table();bm.normal_update()
 originals={v:v.co.copy() for v in bm.verts}
 for v in bm.verts:
  p=originals[v]
  protected=(p.x>.17 and p.z>.21) or p.z<.05 or p.z>.34
  if protected or len(v.link_edges)<3:continue
  avg=sum((originals[e.other_vert(v)] for e in v.link_edges),Vector())/len(v.link_edges)
  delta=(avg-p)*.35
  if delta.length>.0015:delta=delta.normalized()*.0015
  v.co=p+delta
 bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(cat.data);bm.free();cat.data.update()
 for p in cat.data.polygons:p.use_smooth=False
 report={'stage':'geometry facets','subdivision_levels':1,'smooth_blend':.35,'max_displacement_m':.0015,'random_jitter':0,'body_normals':'flat','protected_regions':'reviewed single-case head x>.17,z>.21; paw z<.05; upper ear/tail z>.34','automatic_semantic_masks':False,'parameters_deviation':'gentler smoothing than .6 candidate to preserve silhouette; uniform split for this POC, adaptive remesher not implemented'}
 save_stage(cat,report)
elif stage in ['color','final']:
 bpy.ops.wm.open_mainfile(filepath=str(HERE/GEODIR/'scene.blend'));cat=bpy.data.objects['Cat']
 mat=cat.data.materials[0];p=bsdf(mat);nt=mat.node_tree
 im=bpy.data.images.load(str(HERE/COLORDIR/'facet-color.png'),check_existing=False)
 tex=nt.nodes.new('ShaderNodeTexImage');tex.image=im;nt.links.new(tex.outputs['Color'],p.inputs['Base Color'])
 p.inputs['Metallic'].default_value=0;p.inputs['Roughness'].default_value=.9
 if stage=='final':
  if p.inputs.get('Specular IOR Level'):p.inputs['Specular IOR Level'].default_value=.15
  for link in list(nt.links):
   if link.to_socket==p.inputs['Normal']:nt.links.remove(link)
  roughfile=HERE/COLORDIR/'roughness.png'
  if roughfile.exists():
   rm=bpy.data.images.load(str(roughfile),check_existing=False);rm.colorspace_settings.name='Non-Color'
   rn=nt.nodes.new('ShaderNodeTexImage');rn.image=rm;nt.links.new(rn.outputs['Color'],p.inputs['Roughness'])
 report={'stage':stage,'source_texture':str(HERE/COLORDIR/'facet-color.png'),'metallic':0,'body_roughness':.9,'body_specular_ior_level':.15 if stage=='final' else .5,'normal_map':False,'eyes':'native geometry and texture preserved; no generic eye replacement','rigged':False}
 save_stage(cat,report)

for name,az,el in [('front',0,2),('left',90,2),('right',-90,2),('back',180,2),('threequarter',-38,12),('top',0,89)]:
 render(name,az,el)
render('clay-threequarter',-38,12,clay=True)
render('face',0,5,target=(.20,0,.30),scale=.29)
if SINGLE:
 sc=bpy.context.scene;sc.render.resolution_x=1200;sc.render.resolution_y=900
 render('hero',-69,10,target=(0,0,.20),scale=.79)
 render('face-threequarter',-55,9,target=(.23,0,.29),scale=.28)
 if stage in ['color','final']:
  mat=cat.data.materials[0];nt=mat.node_tree;out=next(n for n in nt.nodes if n.type=='OUTPUT_MATERIAL')
  p=bsdf(mat);em=nt.nodes.new('ShaderNodeEmission');nt.links.new(tex.outputs['Color'],em.inputs['Color']);nt.links.new(em.outputs[0],out.inputs['Surface'])
  render('unlit',-69,10,target=(0,0,.20),scale=.79)
  nt.links.new(p.outputs[0],out.inputs['Surface']);nt.nodes.remove(em)
print('STAGE_COMPLETE',stage,json.dumps(report),flush=True)
