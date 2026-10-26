"""Deterministically restore source appearance on an aligned service-reduced mesh.

No body coordinates, manual masks or identity landmarks are used in this stage.
Source appearance remains a manually assisted upstream research artifact.
"""
import ast,hashlib,json,math,sys,time
from pathlib import Path
import bpy,bmesh,numpy as np
from mathutils import Vector

HERE=Path(__file__).resolve().parent
cfgpath=Path(sys.argv[sys.argv.index('--')+1]);cfg=json.loads(cfgpath.read_text())
source=HERE/cfg['source_file'];root=HERE/cfg['output'];candidate=root/'candidate-aligned'
factor_only='--factor-only' in sys.argv
OUT=root/('factor-only' if factor_only else 'restored');OUT.mkdir(exist_ok=True)
code=Path(__file__).read_bytes();(OUT/'executed-source.py').write_bytes(code)
helpers=ast.parse((HERE/'blender_stage.py').read_text())
exec(compile(ast.Module(body=[n for n in helpers.body if isinstance(n,ast.FunctionDef) and n.name in {'bsdf','make_mat','render','export_npz','mesh_stats'}],type_ignores=[]),'review_helpers','exec'))
report=json.loads((candidate/'render-report.json').read_text())
assert report['budget_pass'] and report['stats']['triangles']==3500
bpy.ops.wm.open_mainfile(filepath=str(source.parent/'scene.blend'))
high=bpy.data.objects['Cat'];high.name='AppearanceSource'
before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(candidate/'cat.glb'))
objs=[o for o in bpy.data.objects if o not in before and o.type=='MESH'];assert len(objs)==1
cat=objs[0];cat.name='Cat'
assert len(high.data.materials)==1 and len(cat.data.materials)==1
for face in cat.data.polygons:face.use_smooth=False
mat=(cat.data.materials[0] if factor_only else high.data.materials[0]).copy();mat.name='RestoredSourceMaterial';cat.data.materials[0]=mat
if factor_only:
    src_bsdf=bsdf(high.data.materials[0]);dst_bsdf=bsdf(mat)
    for socket in ['Metallic','Specular IOR Level']:
        assert not src_bsdf.inputs[socket].is_linked,'Scalar fix requires unlinked source factors'
        for link in list(dst_bsdf.inputs[socket].links):mat.node_tree.links.remove(link)
        dst_bsdf.inputs[socket].default_value=src_bsdf.inputs[socket].default_value
sc=bpy.context.scene;sc.cycles.samples=1
distances=report['sampled_surface_distance'];maximum=max(distances[k]['max_m'] for k in ['source_to_candidate','candidate_to_source'])
original=np.load(source.parent/'mesh.npz');extent=float(np.ptp(original['verts'],axis=0).max())
cage=max(3*maximum,extent*.001)
sc.render.bake.use_selected_to_active=True;sc.render.bake.use_clear=True
sc.render.bake.cage_extrusion=cage;sc.render.bake.max_ray_distance=2*cage;sc.render.bake.margin=16
sc.render.bake.use_pass_direct=False;sc.render.bake.use_pass_indirect=False;sc.render.bake.use_pass_color=True
bpy.ops.object.select_all(action='DESELECT');high.select_set(True);cat.select_set(True);bpy.context.view_layer.objects.active=cat
bakes={}
for name,kind,socket,colorspace in ([] if factor_only else [('base-color','DIFFUSE','Base Color','sRGB'),('roughness','ROUGHNESS','Roughness','Non-Color')]):
    im=bpy.data.images.new('Restored_'+name,width=2048,height=2048,alpha=False);im.colorspace_settings.name=colorspace
    nt=mat.node_tree;tex=nt.nodes.new('ShaderNodeTexImage');tex.image=im
    for n in nt.nodes:n.select=False
    tex.select=True;nt.nodes.active=tex
    start=time.monotonic();bpy.ops.object.bake(type=kind);elapsed=time.monotonic()-start
    im.filepath_raw=str(OUT/(name+'.png'));im.file_format='PNG';im.save()
    nt.links.new(tex.outputs['Color'],bsdf(mat).inputs[socket])
    bakes[name]={'type':kind,'seconds':elapsed,'color_space':colorspace,'resolution':[2048,2048],'format':'PNG'}
bpy.data.objects.remove(high,do_unlink=True);sc.render.bake.use_selected_to_active=False;sc.cycles.samples=24
export_npz(cat,OUT/'mesh.npz');new=np.load(OUT/'mesh.npz');old=np.load(candidate/'mesh.npz')
# Loop triangles may rotate their three indices, so compare world-space corner sets with canonical tuple sorting.
def canonical(data):
    return sorted(tuple(sorted(tuple(float(x) for x in np.round(p,7)) for p in tri)) for tri in data['verts'][data['tris']])
same_geometry=canonical(new)==canonical(old);assert same_geometry
stats=mesh_stats(cat);assert stats['triangles']==3500
report.update({'source_file':str(source.relative_to(HERE)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'input_candidate':str(candidate.relative_to(HERE)),'stage':'automatic material restoration after service decimation',
    'stats':stats,'geometry_unchanged_from_aligned_service_output':same_geometry,'manual_processing_regions':[],
    'uv_reunwrap_performed':False,'material_policy':'Restore source Metallic and Specular IOR Level scalars; flat shading; keep service textures' if factor_only else 'Copy source shader; flat shading; bake source base color and roughness into existing candidate UV',
    'cage_extrusion_m':None if factor_only else cage,'max_ray_distance_m':None if factor_only else 2*cage,'cage_policy':None if factor_only else '3 times maximum sampled surface discrepancy, minimum 0.1% source extent',
    'bake':bakes,'identity_or_art_pass':False,'new_cat_automation_proven':False,'manual_review_pending':True,
    'local_shape_edits':False,'local_material_edits':True,'local_texture_edits':not factor_only,'smooth_polygon_count':0})
# The previous report's container metadata describes the raw service artifact, not this re-export.
report['service_glb_metadata']=report.pop('glb')
(OUT/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);bpy.context.view_layer.objects.active=cat
bpy.ops.export_scene.gltf(filepath=str(OUT/'cat.glb'),export_format='GLB',use_selection=True)
for name,az,el,target,scale in report['views']:render(name,az,el,target=target,scale=scale)
render('opposite-clay',110,10,target=(0,0,.20),scale=.79,clay=True)
print('MATERIAL_RESTORE_COMPLETE',json.dumps({'triangles':stats['triangles'],'geometry_unchanged':same_geometry,'bake':bakes}),flush=True)
