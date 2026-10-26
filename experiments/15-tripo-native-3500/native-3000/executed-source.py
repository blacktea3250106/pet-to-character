"""Compare unedited native GLBs using one documented presentation transform."""
import ast, hashlib, json, math, struct
from pathlib import Path
import bpy, bmesh, numpy as np
from mathutils import Vector

HERE=Path(__file__).resolve().parent
ROOT=HERE/'15-tripo-native-3500'
tree=ast.parse((HERE/'blender_stage.py').read_text())
helpers={'bsdf','make_mat','setup','render','export_npz','mesh_stats'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in helpers],type_ignores=[]),'review_helpers','exec'))

def container_stats(path):
    data=path.read_bytes();assert data[:4]==b'glTF'
    length,kind=struct.unpack_from('<II',data,12);assert kind==0x4e4f534a
    gltf=json.loads(data[20:20+length]);counts=[]
    for mesh in gltf['meshes']:
        n=0
        for primitive in mesh['primitives']:
            assert primitive.get('mode',4)==4,'Only TRIANGLES supported in this audit'
            accessor=primitive.get('indices',primitive['attributes']['POSITION'])
            count=gltf['accessors'][accessor]['count'];assert count%3==0
            n+=count//3
        counts.append(n)
    return {'sha256':hashlib.sha256(data).hexdigest(),'mesh_triangles':counts,
        'unique_mesh_triangles':sum(counts),'mesh_instances':sum('mesh' in n for n in gltf.get('nodes',[])),
        'skins':len(gltf.get('skins',[])),'animations':len(gltf.get('animations',[])),
        'method':'GLB TRIANGLES index accessor count / 3, summed over mesh primitives; independent of UV vertex splitting'}

reports={}
for name,source in [('native-3000',HERE/'05b-tripo/model_url.glb'),('native-3500',ROOT/'model_url.glb')]:
    OUT=ROOT/name;OUT.mkdir(exist_ok=True)
    (OUT/'executed-source.py').write_bytes(Path(__file__).read_bytes())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    objs=[o for o in bpy.context.scene.objects if o.type=='MESH']
    points=np.array([o.matrix_world@v.co for o in objs for v in o.data.vertices]);lo,hi=points.min(0),points.max(0)
    scale=.65/max(hi-lo);offset=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
    for o in objs:
        for v in o.data.vertices:v.co=Vector((np.array(o.matrix_world@v.co)-offset)*scale)
        o.matrix_world.identity()
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:o.select_set(True)
    bpy.context.view_layer.objects.active=objs[0];bpy.ops.object.join();cat=bpy.context.object;cat.name='Cat'
    theta=math.radians(-69.72070751701202)
    rot=np.array([[math.cos(theta),-math.sin(theta),0],[math.sin(theta),math.cos(theta),0],[0,0,1]])
    vv=np.array([v.co[:] for v in cat.data.vertices])@rot.T
    mn,mx=vv.min(0),vv.max(0);factor=.65/max(mx-mn)
    center=np.array([(mn[0]+mx[0])/2,(mn[1]+mx[1])/2,mn[2]])
    for vertex,point in zip(cat.data.vertices,vv):vertex.co=Vector((point-center)*factor)
    setup();sc=bpy.context.scene
    sc.render.resolution_x=1000;sc.render.resolution_y=750;sc.cycles.samples=24
    sc.view_settings.look='None'
    report={'source':str(source.relative_to(HERE)),'container':container_stats(source),'stats':mesh_stats(cat),
        'geometry_edits':False,'decimation':False,'reference_geometry_transform':{'rotation_z_degrees':-69.72070751701202,'normalized_max_extent_m':.65,'note':'Same manually established baseline rotation for both, not automatic orientation estimation'},
        'texture_edits':False,'material_edits':False,'normals_edits':False,
        'identity_or_art_pass':False,'animation_validated':False,'new_cat_automation_proven':False}
    assert report['container']['unique_mesh_triangles']==report['stats']['triangles']
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    export_npz(cat,OUT/'mesh.npz')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
    for view,az,el,target,ortho in [('hero',-69,10,(0,0,.20),.79),('opposite',110,10,(0,0,.20),.79)]:
        render(view,az,el,target=target,scale=ortho)
    render('clay',-69,10,target=(0,0,.20),scale=.79,clay=True)
    reports[name]=report
(ROOT/'native-comparison.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2))
print(json.dumps({k:v['stats']['triangles'] for k,v in reports.items()}),flush=True)
