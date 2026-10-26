"""Blender: change only shading and verify the actual exported GLB on reimport."""
import argparse,hashlib,itertools,json,sys
from pathlib import Path
import bpy,numpy as np
from mathutils.kdtree import KDTree

parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);source=args.source.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
def snapshot():
    triangles=[];uvs=[];normals=[];images=[]
    for obj in bpy.context.scene.objects:
        if obj.type!='MESH':continue
        me=obj.data;me.calc_loop_triangles();rotation=obj.matrix_world.to_3x3().inverted().transposed()
        for tri in me.loop_triangles:
            triangles.append([obj.matrix_world@me.vertices[i].co for i in tri.vertices])
            uvs.append([me.uv_layers.active.data[i].uv[:] for i in tri.loops])
            normals.append([(rotation@me.corner_normals[i].vector).normalized()[:] for i in tri.loops])
    used_images={node.image for obj in bpy.context.scene.objects if obj.type=='MESH'
                 for mat in obj.data.materials if mat and mat.use_nodes
                 for node in mat.node_tree.nodes if node.type=='TEX_IMAGE' and node.image}
    if not used_images:raise RuntimeError('No shader-referenced texture images; cannot validate appearance')
    for image in used_images:
        size=list(image.size)  # Force the packed image to decode before checking pixels.
        if min(size)<=0 or len(image.pixels)==0:raise RuntimeError('Texture pixel buffer is not loaded')
        pixels=np.empty(len(image.pixels),np.float32);image.pixels.foreach_get(pixels)
        images.append({'size':size,'sha256_decoded_rgba32':hashlib.sha256(pixels.tobytes()).hexdigest()})
    return np.array(triangles),np.array(uvs),np.array(normals),sorted(images,key=lambda x:x['sha256_decoded_rgba32'])
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
before,uv_before,_,images_before=snapshot()
for obj in bpy.context.scene.objects:
    if obj.type=='MESH':
        for poly in obj.data.polygons:poly.use_smooth=False
        obj.data.update()
        face_normals=[None]*len(obj.data.loops)
        for poly in obj.data.polygons:
            for loop in poly.loop_indices:face_normals[loop]=poly.normal.copy()
        obj.data.normals_split_custom_set(face_normals)
        obj.data.update()
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.context.scene.objects:
    if obj.type=='MESH':obj.select_set(True);bpy.context.view_layer.objects.active=obj
destination=out/'cat.glb'
bpy.ops.export_scene.gltf(filepath=str(destination),export_format='GLB',use_selection=True)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(destination))
after,uv_after,normals,images_after=snapshot()
if len(before)!=len(after):raise RuntimeError('Triangle count changed')
centers=before.mean(1);tree=KDTree(len(centers))
for i,point in enumerate(centers):tree.insert(point,i)
tree.balance();permutations=list(itertools.permutations(range(3)))
mapping=[];max_position=0.;max_uv=0.
for tri,uv in zip(after,uv_after):
    _,idx,_=tree.find(tri.mean(0));mapping.append(idx)
    candidates=np.array([before[idx][list(order)] for order in permutations])
    errors=np.linalg.norm(candidates-tri,axis=2).max(1);best=int(errors.argmin())
    max_position=max(max_position,float(errors[best]))
    max_uv=max(max_uv,float(np.abs(uv_before[idx][list(permutations[best])]-uv).max()))
face=np.cross(after[:,1]-after[:,0],after[:,2]-after[:,0]);length=np.linalg.norm(face,axis=1)
valid=length>1e-12;face[valid]/=length[valid,None]
normal_dot=np.einsum('tvc,tc->tv',normals[valid],face[valid]);minimum_dot=float(normal_dot.min())
passed=len(set(mapping))==len(before) and max_position<1e-6 and max_uv<1e-6 and images_before==images_after and minimum_dot>.9999
report={'source':str(source),'source_sha256':source_hash,'candidate_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'triangles':len(after),'target_triangles':3500,'budget_pass':len(after)<=3500,
        'unique_triangle_correspondence':len(set(mapping))==len(before),'max_corner_position_difference_source_units':max_position,
        'max_corner_uv_difference':max_uv,'decoded_texture_hashes_identical':images_before==images_after,'texture_images':images_after,
        'minimum_exported_corner_normal_dot_geometric_face_normal':minimum_dot,'nondegenerate_triangles_checked':int(valid.sum()),
        'source_file_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==source_hash,
        'shading_export_roundtrip_pass':passed,'method':'Nearest triangle-centroid correspondence, six corner permutations, UV correspondence and exact decoded pixel hashes; geometric normal dot-product after actual GLB reimport',
        'scope':'Shading-only candidate. No geometry reduction, coat recolor, eye control or rigging. Technical pass is not final art acceptance.',
        'art_pass':False,'animation_pass':False,'new_cat_automation_proven':False}
(out/'export-review.json').write_text(json.dumps(report,indent=2));(out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
print('FLAT_EXPORT_REVIEW',json.dumps(report),flush=True)
if not passed:raise RuntimeError('Flat export verification failed; candidate not accepted')
