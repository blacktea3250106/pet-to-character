"""Audit rest intersections and bone-axis mismatch independently of animation playback."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

P=Path(__file__).resolve().parent
source=json.loads((P.parent/'27-animation-compatibility/inventory/report.json').read_text())['source']
C=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])

def segment_hit(a,b,tri,span):
 e1,e2=tri[1]-tri[0],tri[2]-tri[0];direction=b-a;h=np.cross(direction,e2);det=e1@h
 if abs(det)<span**3*1e-12:return False
 inv=1/det;s=a-tri[0];u=inv*(s@h)
 if not 1e-6<u<1-1e-6:return False
 q=np.cross(s,e1);v=inv*(direction@q)
 if v<=1e-6 or u+v>=1-1e-6:return False
 t=inv*(e2@q)
 return 1e-6<t<1-1e-6

def crossing_pairs(v,f):
 span=np.ptp(v,axis=0).max();_,weld=np.unique(np.rint(v/(span*1e-7)).astype(np.int64),axis=0,return_inverse=True)
 tree=BVHTree.FromPolygons([Vector(p) for p in v],f.tolist(),all_triangles=True);pairs=set()
 for i,j in tree.overlap(tree):
  if i>=j or np.isin(weld[f[i]],weld[f[j]]).any():continue
  a,b=v[f[i]],v[f[j]]
  if any(segment_hit(a[k],a[(k+1)%3],b,span) or segment_hit(b[k],b[(k+1)%3],a,span) for k in range(3)):pairs.add((i,j))
 return pairs

def inside(point,vertices,faces):
 tris=vertices[faces];a=tris[:,0];e1=tris[:,1]-a;e2=tris[:,2]-a;votes=[]
 for direction in np.array([[1.,.371,.219],[.183,1.,.417],[.271,.153,1.]]):
  direction/=np.linalg.norm(direction);h=np.cross(direction,e2);det=np.sum(e1*h,axis=1);inv=np.divide(1,det,out=np.zeros_like(det),where=np.abs(det)>1e-12)
  s=point-a;u=inv*np.sum(s*h,axis=1);q=np.cross(s,e1);v=inv*(q@direction);t=inv*np.sum(e2*q,axis=1)
  hits=t[(np.abs(det)>1e-12)&(u>=0)&(v>=0)&(u+v<=1)&(t>1e-6)]
  unique=np.unique(np.round(hits,7));votes.append(bool(len(unique)%2))
 return sum(votes)>=2,votes

results=[]
for folder in sorted((P/'fit-v002').iterdir()):
 if not (folder/'fit.npz').exists():continue
 d=np.load(folder/'fit.npz');r=json.loads((folder/'fit.json').read_text());v=d['target_vertices'];f=d['target_triangles'];joint=[]
 for bone in source['bones']:
  if bone['name']=='root':continue
  j=r['joints'][bone['name']];direction=np.array(j['tail'])-j['head'];direction/=max(np.linalg.norm(direction),1e-12)
  axis=C@np.array(bone['rest_world'])[:3,1];axis/=np.linalg.norm(axis)
  angle=float(np.rad2deg(np.arccos(np.clip(axis@direction,-1,1))))
  is_inside,votes=inside(np.array(j['head']),v,f)
  joint.append({'bone':bone['name'],'mapped_head_inside_target':is_inside,'ray_votes':votes,'retained_axis_vs_mapped_bone_degrees':angle})
 base_pairs=crossing_pairs(d['source_initial'],d['source_triangles'])
 fitted_pairs=crossing_pairs(d['source_wrapped'],d['source_triangles'])
 new_pairs=fitted_pairs-base_pairs
 flabel=[r['parts'][np.bincount(d['source_labels'][face],minlength=7).argmax()] for face in d['source_triangles']]
 regions=Counter('/'.join(sorted([flabel[i],flabel[j]])) for i,j in new_pairs)
 result={'case':folder.name,'target_rest_crossing_pairs':len(crossing_pairs(v,f)),
         'scaffold_initial_crossing_pairs':len(base_pairs),'scaffold_rest_crossing_pairs':len(fitted_pairs),
         'new_scaffold_crossing_pairs':len(new_pairs),'new_scaffold_crossing_regions':dict(regions),
         'joints':joint,'limitations':['Bone controls/helper bones need not all lie inside skin; ray parity alone is not anatomical acceptance.',
          'Strict crossing check excludes tangent/coplanar contact and may miss degeneracies.','Scaffold may include source mouth/internal geometry; not every crossing is newly introduced.']}
 if (folder/'rest-audit.json').exists() and not (folder/'rest-audit-initial.json').exists():
  (folder/'rest-audit-initial.json').write_bytes((folder/'rest-audit.json').read_bytes())
 (folder/'rest-audit.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
 print(json.dumps({'case':folder.name,'target_crossings':result['target_rest_crossing_pairs'],'scaffold_crossings':result['scaffold_rest_crossing_pairs'],
                   'initial_scaffold_crossings':len(base_pairs),'new_crossing_regions':dict(regions),
                   'tail_axis_degrees':[round(j['retained_axis_vs_mapped_bone_degrees'],1) for j in joint if 'tail.' in j['bone']]}),flush=True)
(P/'rest-audit-summary.json').write_text(json.dumps({'cases':results},indent=2)+'\n')
