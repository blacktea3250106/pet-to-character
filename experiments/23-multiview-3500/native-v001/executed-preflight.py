"""Read-only GLB metadata budget gate. Does not grant geometry, identity or art acceptance."""
import argparse,hashlib,json,struct
from pathlib import Path

def inspect_glb(path,triangle_limit):
    blob=Path(path).read_bytes()
    if len(blob)<20:raise ValueError('Truncated GLB')
    magic,version,total=struct.unpack_from('<4sII',blob)
    if magic!=b'glTF' or version!=2 or total!=len(blob):raise ValueError('Invalid GLB header/version/length')
    length,kind=struct.unpack_from('<II',blob,12)
    if kind!=0x4e4f534a or 20+length>len(blob):raise ValueError('Invalid JSON chunk')
    d=json.loads(blob[20:20+length]);mesh_counts=[];unsupported=[]
    for mi,mesh in enumerate(d.get('meshes',[])):
        count=0
        for pi,primitive in enumerate(mesh['primitives']):
            mode=primitive.get('mode',4)
            if mode!=4:
                unsupported.append({'mesh':mi,'primitive':pi,'mode':mode});continue
            accessor=primitive.get('indices',primitive['attributes']['POSITION'])
            n=d['accessors'][accessor]['count']
            if not isinstance(n,int) or n<0 or n%3:raise ValueError('Invalid TRIANGLES accessor count')
            count+=n//3
        mesh_counts.append(count)
    scenes=d.get('scenes',[]);scene_index=d.get('scene',0);instances=[]
    if not scenes:raise ValueError('No scene; cannot determine active instances')
    def walk(index,ancestors):
        if index in ancestors:raise ValueError('Scene graph cycle')
        node=d['nodes'][index]
        if 'mesh' in node:instances.append({'node':index,'mesh':node['mesh'],'triangles':mesh_counts[node['mesh']]})
        for child in node.get('children',[]):walk(child,ancestors|{index})
    for root in scenes[scene_index].get('nodes',[]):walk(root,set())
    actual=sum(x['triangles'] for x in instances)
    count_supported=bool(instances) and not unsupported
    return {'file':str(path),'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'scene_index':scene_index,
        'mesh_triangle_counts':mesh_counts,'active_mesh_instances':instances,'active_scene_triangles':actual if count_supported else None,
        'unique_mesh_triangles':sum(mesh_counts),'unsupported_primitives':unsupported,'triangle_limit':triangle_limit,
        'budget_pass':count_supported and 0<actual<=triangle_limit,
        'status':'budget_pass' if count_supported and 0<actual<=triangle_limit else 'budget_rejected' if count_supported else 'unsupported',
        'method':'TRIANGLES accessor count / 3 for each active scene mesh instance; index positions are not decoded here',
        'skins':len(d.get('skins',[])),'animations':len(d.get('animations',[])),
        'asset_accepted':False,'not_validated':['buffer/index integrity beyond JSON metadata','manifoldness and self-intersections','anatomy','photo identity','cat.png style','UV fidelity','skin deformation and source-animation compatibility']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('model',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--triangle-limit',type=int,required=True);args=parser.parse_args()
    report=inspect_glb(args.model,args.triangle_limit)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['active_scene_triangles','budget_pass','status']}))
