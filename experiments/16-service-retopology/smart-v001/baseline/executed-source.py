"""Review service output against its source, without manual regions or shape edits."""
import argparse,ast,hashlib,json,math,struct,sys
from pathlib import Path
import bpy,bmesh,numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('config',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
cfg=json.loads(args.config.read_text());source=HERE/cfg['source_file'];root=HERE/cfg['output']
download=root/'model_url.glb';assert download.exists()
tree=ast.parse((HERE/'blender_stage.py').read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'bsdf','make_mat','render','export_npz','mesh_stats'}],type_ignores=[]),'review_helpers','exec'))
views=[['hero',-69,10,[0,0,.20],.79],['face',-69,9,[.23,0,.31],.28],['opposite',110,10,[0,0,.20],.79],['back-high',110,48,[0,0,.20],.79]]

def direct_count(path):
    blob=path.read_bytes();assert blob[:4]==b'glTF'
    size,kind=struct.unpack_from('<II',blob,12);assert kind==0x4e4f534a
    d=json.loads(blob[20:20+size]);counts=[]
    for mesh in d['meshes']:
        count=0
        for p in mesh['primitives']:
            assert p.get('mode',4)==4
            n=d['accessors'][p.get('indices',p['attributes']['POSITION'])]['count'];assert n%3==0
            count+=n//3
        counts.append(count)
    return {'triangles':sum(counts),'mesh_count':len(counts),'skins':len(d.get('skins',[])),'animations':len(d.get('animations',[])),
        'materials':d.get('materials',[]),'image_count':len(d.get('images',[]))}

def distance_samples(v,t,rv,rt):
    bvh=BVHTree.FromPolygons([Vector(p) for p in rv],rt.tolist(),all_triangles=True)
    points=np.concatenate([v,v[t].mean(1)])
    values=np.array([bvh.find_nearest(Vector(p))[3] for p in points])
    return {'max_m':float(values.max()),'p95_m':float(np.percentile(values,95)),'mean_m':float(values.mean()),'samples':len(points)}

results={}
for variant in ['baseline','candidate']:
    OUT=root/variant;OUT.mkdir(exist_ok=True)
    (OUT/'executed-source.py').write_bytes(Path(__file__).read_bytes())
    bpy.ops.wm.open_mainfile(filepath=str(source.parent/'scene.blend'))
    if variant=='candidate':
        bpy.data.objects.remove(bpy.data.objects['Cat'],do_unlink=True)
        before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(download))
        objs=[o for o in bpy.data.objects if o not in before and o.type=='MESH']
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            for v in o.data.vertices:v.co=o.matrix_world@v.co
            o.matrix_world.identity();o.select_set(True)
        bpy.context.view_layer.objects.active=objs[0]
        if len(objs)>1:bpy.ops.object.join()
        cat=bpy.context.object;cat.name='Cat'
    else:cat=bpy.data.objects['Cat']
    sc=bpy.context.scene;sc.cycles.samples=24
    export_npz(cat,OUT/'mesh.npz');mesh=np.load(OUT/'mesh.npz');v,t=mesh['verts'],mesh['tris']
    stats=mesh_stats(cat);container=direct_count(source if variant=='baseline' else download)
    assert container['triangles']==stats['triangles']
    report={'variant':variant,'source_file':str(source.relative_to(HERE)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'service_output_sha256':hashlib.sha256(download.read_bytes()).hexdigest(),'stats':stats,'glb':container,
        'bounds_m':[v.min(0).tolist(),v.max(0).tolist()],'smooth_polygon_count':sum(f.use_smooth for f in cat.data.polygons),
        'manual_processing_regions':[],'local_geometry_edits':False,'local_material_edits':False,'local_texture_edits':False,
        'automatic_alignment_applied':False,'views':views,'identity_or_art_pass':False,'animation_compatibility':'not_tested','new_cat_automation_proven':False}
    if variant=='candidate':
        original=np.load(root/'baseline/mesh.npz');ov,ot=original['verts'],original['tris']
        report['sampled_surface_distance']={'source_to_candidate':distance_samples(ov,ot,v,t),'candidate_to_source':distance_samples(v,t,ov,ot),
            'scope':'Unaligned world-space vertices and triangle centroids only; not continuous Hausdorff maximum or deformation validation'}
        report['budget_pass']=stats['triangles']<=cfg['parameters']['face_limit']
        (OUT/'cat.glb').write_bytes(download.read_bytes())
    (OUT/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
    for name,az,el,target,scale in views:render(name,az,el,target=target,scale=scale)
    render('opposite-clay',110,10,target=(0,0,.20),scale=.79,clay=True)
    results[variant]=report
(root/'comparison.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('MODEL_PROCESSING_REVIEW_COMPLETE',json.dumps({k:v['stats']['triangles'] for k,v in results.items()}),flush=True)
