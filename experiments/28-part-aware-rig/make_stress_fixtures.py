"""Explicit synthetic geometry stress fixtures, never presented as other real cats."""
from pathlib import Path
import json
import numpy as np
from scipy.sparse import coo_matrix, diags

P=Path(__file__).resolve().parent;out=P/'stress-inputs';out.mkdir(exist_ok=False)
d=np.load(P/'fit-v002/original/fit.npz');report=json.loads((P/'fit-v002/original/fit.json').read_text())
v=d['target_vertices'];f=d['target_triangles'];span=np.ptp(v,axis=0).max()
_,first,inv=np.unique(np.rint(v/(span*1e-7)).astype(np.int64),axis=0,return_index=True,return_inverse=True)
w=v[first];wf=inv[f];edges=np.unique(np.sort(np.vstack([wf[:,[0,1]],wf[:,[1,2]],wf[:,[2,0]]]),axis=1),axis=0)
edges=np.vstack([edges,edges[:,::-1]]);graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(w),len(w))).tocsr();degree=np.asarray(graph.sum(1)).ravel()
mask=(d['target_labels'][first]==0).astype(float)
for _ in range(8):mask=.5*mask+.5*(graph@mask)/degree
center=np.average(w,axis=0,weights=mask)
z0=w[:,2].min();leg_height=report['body_merge_height']-z0
cases=[('short_legs',.75,1),('long_legs',1.25,1),('thin_body',1,.8),('fat_body',1,1.25),('short_fat',.75,1.25)]
results=[]
for name,leg,body in cases:
 q=w.copy()
 # Bend-free continuous z map: limbs change height, everything above moves together.
 dz=np.minimum(np.maximum(q[:,2]-z0,0),leg_height)
 q[:,2]+=(leg-1)*dz
 moved_center=center.copy();moved_center[2]+=(leg-1)*leg_height
 for axis in [1,2]:q[:,axis]+=(body-1)*mask*(q[:,axis]-moved_center[axis])
 vertices=q[inv]
 np.savez_compressed(out/(name+'.npz'),vertices=vertices,triangles=f)
 ratio=np.linalg.norm(np.cross(vertices[f[:,1]]-vertices[f[:,0]],vertices[f[:,2]]-vertices[f[:,0]]),axis=1)/np.maximum(np.linalg.norm(np.cross(v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]),axis=1),1e-12)
 assert ratio.min()>.05
 results.append({'case':name,'leg_height_factor':leg,'torso_expansion_factor':body,'triangles':len(f),'min_area_ratio':float(ratio.min()),'path':name+'.npz'})
(out/'manifest.json').write_text(json.dumps({'kind':'synthetic_same_topology_stress_fixtures','cases':results,
 'fixture_creation':'Part mask automatically derived from original geometry; no manual painted mask. Mask used only to create fixtures, not provided to fitting.',
 'limits':['Not independently generated cats; no generalization success claim.', 'Geometry functions are controlled stress inputs, not photo-derived personalization.', 'Original model remains unchanged.'],
 'ground':float(z0),'leg_height_proxy':float(leg_height)},indent=2)+'\n')
(out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(results),flush=True)
