"""Review service output against its source, without manual regions or shape edits."""
import argparse,ast,hashlib,json,math,struct,sys
from pathlib import Path
import bpy,bmesh,numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('config',type=Path);parser.add_argument('--align-bounds',action='store_true');parser.add_argument('--baseline-cache',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
cfg=json.loads(args.config.read_text());source=HERE/cfg['source_file'];root=HERE/cfg['output']
baseline_dir=args.baseline_cache or root/'baseline'
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
variants=['baseline','candidate-aligned' if args.align_bounds else 'candidate']
for variant in variants:
    if variant=='baseline' and args.align_bounds and (baseline_dir/'render-report.json').exists():
        report=json.loads((baseline_dir/'render-report.json').read_text())
        assert report['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
        assert report['views']==views
        results[variant]=report;continue
    OUT=root/variant;OUT.mkdir(exist_ok=True)
    (OUT/'executed-source.py').write_bytes(Path(__file__).read_bytes())
    bpy.ops.wm.open_mainfile(filepath=str(source.parent/'scene.blend'))
    alignment=None
    if variant!='baseline':
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
        if args.align_bounds:
            reference=np.load(source.parent/'mesh.npz')['verts']
            points=np.array([v.co[:] for v in cat.data.vertices])
            input_center=(reference.min(0)+reference.max(0))/2
            output_center=(points.min(0)+points.max(0))/2
            scale=float(np.ptp(reference,axis=0).max()/np.ptp(points,axis=0).max())
            for vertex,point in zip(cat.data.vertices,points):vertex.co=Vector((point-output_center)*scale+input_center)
            alignment={'method':'Restore source bounding-box center and longest extent with one uniform scale; no rotation or per-axis deformation',
                'scale':scale,'service_center':output_center.tolist(),'source_center':input_center.tolist(),
                'manual_landmarks_or_regions':False,'orientation_assumption':'Service retained source axes; unverified rotations would fail surface/visual checks'}
    else:cat=bpy.data.objects['Cat']
    sc=bpy.context.scene;sc.cycles.samples=24
    export_npz(cat,OUT/'mesh.npz');mesh=np.load(OUT/'mesh.npz');v,t=mesh['verts'],mesh['tris']
    stats=mesh_stats(cat);container=direct_count(source if variant=='baseline' else download)
    assert container['triangles']==stats['triangles']
    report={'variant':variant,'source_file':str(source.relative_to(HERE)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'service_output_sha256':hashlib.sha256(download.read_bytes()).hexdigest(),'stats':stats,'glb':container,
        'bounds_m':[v.min(0).tolist(),v.max(0).tolist()],'smooth_polygon_count':sum(f.use_smooth for f in cat.data.polygons),
        'manual_processing_regions':[],'local_shape_edits':False,'local_material_edits':False,'local_texture_edits':False,
        'automatic_alignment_applied':alignment is not None,'alignment':alignment,'views':views,'identity_or_art_pass':False,'animation_compatibility':'not_tested','new_cat_automation_proven':False}
    if variant!='baseline':
        original=np.load(baseline_dir/'mesh.npz');ov,ot=original['verts'],original['tris']
        report['baseline_cache']=str(baseline_dir.relative_to(HERE))
        report['sampled_surface_distance']={'source_to_candidate':distance_samples(ov,ot,v,t),'candidate_to_source':distance_samples(v,t,ov,ot),
            'scope':'Unaligned world-space vertices and triangle centroids only; not continuous Hausdorff maximum or deformation validation'}
        report['budget_pass']=stats['triangles']<=cfg['parameters']['face_limit']
        if alignment is None:(OUT/'cat.glb').write_bytes(download.read_bytes())
        else:
            bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);bpy.context.view_layer.objects.active=cat
            bpy.ops.export_scene.gltf(filepath=str(OUT/'cat.glb'),export_format='GLB',use_selection=True)
    (OUT/'render-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'scene.blend'))
    for name,az,el,target,scale in views:render(name,az,el,target=target,scale=scale)
    render('opposite-clay',110,10,target=(0,0,.20),scale=.79,clay=True)
    results[variant]=report
(root/('comparison-aligned.json' if args.align_bounds else 'comparison.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2))
print('MODEL_PROCESSING_REVIEW_COMPLETE',json.dumps({k:v['stats']['triangles'] for k,v in results.items()}),flush=True)
