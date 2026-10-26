"""Read-only, cat-independent geometry measurements. Never grants an art/anatomy pass.

uv-split render vertices are welded only in the analysis copy. Input NPZ is untouched.
Usage: uv run --with numpy python inspect_geometry.py MESH.npz REPORT.json
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

def inspect(path):
    data=np.load(path,allow_pickle=False);v=data['verts'].astype(float);t=data['tris'].astype(int)
    if v.ndim!=2 or v.shape[1]!=3 or t.ndim!=2 or t.shape[1]!=3:raise ValueError('Expected Vx3 positions and Fx3 triangles')
    if not np.isfinite(v).all() or t.min()<0 or t.max()>=len(v):raise ValueError('Invalid vertex coordinates or triangle indices')
    extent=float(np.ptp(v,axis=0).max());tolerance=max(extent*1e-6,1e-12)
    # Quantized analysis welding can differ at bucket boundaries; tolerance is recorded.
    _,idx,inv=np.unique(np.round(v/tolerance).astype(np.int64),axis=0,return_index=True,return_inverse=True)
    w=v[idx];f=inv[t]
    parent=np.arange(len(w))
    def root(a):
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for tri in f:
        for x in tri[1:]:parent[root(x)]=root(tri[0])
    labels=np.array([root(i) for i in range(len(w))]);fl=labels[f[:,0]]
    normal=np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]])
    twice_area=np.linalg.norm(normal,axis=1)
    edges=np.sort(np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    components=[]
    for label in np.unique(labels):
        pts=w[labels==label];faces=np.where(fl==label)[0]
        eigen=np.maximum(np.linalg.eigvalsh(np.cov(pts.T)) if len(pts)>1 else np.zeros(3),0)
        elongation=float(np.sqrt(eigen[-1]/max(eigen[-2],tolerance*tolerance)))
        components.append({'vertex_count':len(pts),'triangle_count':len(faces),'center':pts.mean(0).tolist(),
          'bounds':[pts.min(0).tolist(),pts.max(0).tolist()],'principal_elongation':elongation,
          'fraction_triangles':float(len(faces)/len(t))})
    components.sort(key=lambda c:-c['triangle_count'])
    candidates=[i for i,c in enumerate(components) if i>0 and c['fraction_triangles']<.01]
    uv=data['tri_uv'] if 'tri_uv' in data else None
    return {'input':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'measurement_scope':'Topology and component measurements only; no semantic or artistic acceptance',
      'render_vertices':len(v),'analysis_vertices':len(w),'triangles':len(t),'weld_tolerance':tolerance,
      'weld_method':'quantized coordinates; analysis copy only','boundary_edges':int((counts==1).sum()),
      'edges_with_more_than_two_faces':int((counts>2).sum()),'degenerate_triangles':int((twice_area<extent**2*1e-12).sum()),
      'component_count':len(components),'components':components,
      'uv_finite':bool(np.isfinite(uv).all()) if uv is not None else None,
      'uv_outside_unit_square_corners':int(((uv<0)|(uv>1)).any(-1).sum()) if uv is not None else None,
      'small_component_review_candidates':candidates,'candidate_policy':'Flag for semantic review, NEVER auto-delete; separate eyes, teeth or accessories can be intentional',
      'anatomy_pass':None,'identity_pass':None,'style_pass':None,'automatic_repair_performed':False,
      'not_evaluated':['self intersections','correct leg count and anatomy','UV overlap','photo identity','facet aesthetics','skin deformation','animation','engine appearance']}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mesh',type=Path);parser.add_argument('report',type=Path);args=parser.parse_args()
    before=hashlib.sha256(args.mesh.read_bytes()).hexdigest();report=inspect(args.mesh)
    assert hashlib.sha256(args.mesh.read_bytes()).hexdigest()==before
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:report[k] for k in ['triangles','boundary_edges','edges_with_more_than_two_faces','component_count','small_component_review_candidates']},ensure_ascii=False))
if __name__=='__main__':main()
