"""Bounded geodesic/part-aware surface fitting. This is a research initializer.

No target hand landmarks. Source skeleton semantics are a one-time template rule.
Source skin is the transfer scaffold; the target render mesh is never wrapped.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix, diags, eye
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.sparse.linalg import spsolve
from scipy.spatial import cKDTree

P = Path(__file__).resolve().parent
OLD = P.parent / '27-animation-compatibility'
PARTS = ['body', 'front_L', 'front_R', 'rear_L', 'rear_R', 'head', 'tail']
C = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])


def bone_part(name):
    if 'tail.' in name:
        return 'tail'
    if any(s in name for s in ['shoulder.', 'upper_arm.', 'forearm.', 'hand.', 'f_toe.']):
        return 'front_' + ('L' if '.L' in name else 'R')
    if any(s in name for s in ['thigh.', 'shin.', 'foot.', 'r_toe.']):
        return 'rear_' + ('L' if '.L' in name else 'R')
    if any(s in name for s in ['jaw', 'tongue', 'eye', 'ear.']) or name in ['DEF-spine.005', 'DEF-spine.006']:
        return 'head'
    return 'body'


def graph_mesh(vertices, triangles):
    span = np.ptp(vertices, axis=0).max()
    _, first, inv = np.unique(np.rint(vertices / (span*1e-7)).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    v, f = vertices[first], inv[triangles]
    edges = np.unique(np.sort(np.vstack([f[:,[0,1]], f[:,[1,2]], f[:,[2,0]]]), axis=1), axis=0)
    edges = edges[edges[:,0] != edges[:,1]]
    e = np.vstack([edges, edges[:,::-1]])
    length = np.linalg.norm(v[e[:,0]] - v[e[:,1]], axis=1)
    g = coo_matrix((length, (e[:,0], e[:,1])), shape=(len(v),len(v))).tocsr()
    n, labels = connected_components(g, directed=False)
    ids = np.flatnonzero(labels == np.argmax(np.bincount(labels)))
    remap = np.full(len(v), -1, int); remap[ids] = np.arange(len(ids))
    kept = np.all(remap[f] >= 0, axis=1)
    return {'v':v[ids], 'f':remap[f[kept]], 'g':g[ids][:,ids],
            'original_ids':first[ids], 'render_to_welded':remap[inv],
            'components':n, 'excluded_vertices':len(v)-len(ids), 'span':span}


def feet(mesh):
    v,g=mesh['v'],mesh['g']; z0=v[:,2].min(); height=np.ptp(v[:,2])
    candidates=[]
    for fraction in np.arange(.04,.661,.02):
        ids=np.flatnonzero(v[:,2] <= z0 + fraction*height)
        n,lab=connected_components(g[ids][:,ids],directed=False)
        groups=[ids[lab==i] for i in range(n) if (lab==i).sum()>=5]
        if len(groups)==4: candidates.append((float(fraction),groups))
        elif candidates and len(groups)<4: break
    if len(candidates)<3: raise ValueError('Four separated low limbs not stable')
    groups=candidates[0][1];centers=np.array([np.median(v[q],axis=0) for q in groups]);order=np.argsort(centers[:,0])
    result={}
    for label,pair in [('rear',order[:2]),('front',order[2:])]:
        for side,i in zip(['R','L'],pair[np.argsort(centers[pair,1])]):
            group=groups[i]; center=centers[i].copy();center[2]=z0
            seed=group[np.argmin(np.linalg.norm(v[group]-center,axis=1))]
            result[label+'_'+side]={'point':center,'seed':int(seed),'group':group}
    return result,float(z0+candidates[-1][0]*height)


def descriptors(mesh):
    v,g=mesh['v'],mesh['g']; fs,merge=feet(mesh)
    keys=['front_L','front_R','rear_L','rear_R']
    seeds=[fs[k]['seed'] for k in keys]
    d4=dijkstra(g,indices=seeds,directed=False)
    midx=np.mean([fs[k]['point'][0] for k in keys])
    eligible=(v[:,0]<midx)&(v[:,2]>v[:,2].min()+.15*np.ptp(v[:,2]))
    if not eligible.any(): raise ValueError('No rear extremity candidate')
    score=np.where(eligible,np.min(d4,axis=0),-1)
    tail=int(score.argmax())
    nose=int(v[:,0].argmax())
    seeds += [nose,tail]
    dist=dijkstra(g,indices=seeds,directed=False).T
    if not np.isfinite(dist).all():raise ValueError('Disconnected main surface')
    # Normalize intrinsic distances per terminal; retain all six constraints.
    feature=dist / np.max(dist,axis=0)[None,:]
    return {'feet':fs,'merge':merge,'seeds':seeds,'features':feature,'distances':dist,
            'tail_candidate':tail,'nose_candidate':nose}


def closest_triangles(points, triangles):
    """Exact projection to all candidate triangles in arbitrary Euclidean dimension."""
    a=triangles[:,0];u=triangles[:,1]-a;v=triangles[:,2]-a
    rel=points[:,None,:]-a[None,:,:]
    uu=np.sum(u*u,axis=1);uv=np.sum(u*v,axis=1);vv=np.sum(v*v,axis=1)
    ru=np.sum(rel*u[None,:,:],axis=2);rv=np.sum(rel*v[None,:,:],axis=2)
    den=np.maximum(uu*vv-uv*uv,1e-20)
    s=(ru*vv-rv*uv)/den;t=(rv*uu-ru*uv)/den
    bary=np.stack([1-s-t,s,t],axis=2)
    projected=a[None,:,:]+s[:,:,None]*u[None,:,:]+t[:,:,None]*v[None,:,:]
    cost=np.sum((points[:,None,:]-projected)**2,axis=2)
    cost[np.any(bary<0,axis=2)]=np.inf
    for i,j in [(0,1),(1,2),(2,0)]:
        start=triangles[:,i];edge=triangles[:,j]-start
        f=np.clip(np.sum((points[:,None,:]-start[None,:,:])*edge[None,:,:],axis=2)/np.maximum(np.sum(edge*edge,axis=1),1e-20),0,1)
        q=start[None,:,:]+f[:,:,None]*edge[None,:,:]
        ecost=np.sum((points[:,None,:]-q)**2,axis=2);better=ecost<cost
        bc=np.zeros_like(bary);bc[:,:,i]=1-f;bc[:,:,j]=f
        projected[better]=q[better];bary[better]=bc[better];cost[better]=ecost[better]
    ti=cost.argmin(axis=1);rows=np.arange(len(points))
    return ti,bary[rows,ti],projected[rows,ti]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',default='original');ap.add_argument('--target-npz');ap.add_argument('--output',default='fit-v001');ap.add_argument('--arap',action='store_true')
    args=ap.parse_args();out=P/args.output/args.case
    if out.exists():raise RuntimeError('Preserve prior fit')
    out.mkdir(parents=True)
    (out/'executed-source.py').write_bytes(Path(__file__).read_bytes())
    inventory=json.loads((OLD/'inventory/report.json').read_text())
    source=np.load(OLD/'inventory/source-mesh.npz')
    target=np.load(args.target_npz or OLD/'inventory/target-mesh.npz')
    s0=source['vertices']@C.T; t0=target['vertices']
    sm=graph_mesh(s0,source['triangles']);tm=graph_mesh(t0,target['triangles'])
    sd=descriptors(sm);td=descriptors(tm)
    keys=['front_L','front_R','rear_L','rear_R']
    a=np.array([sd['feet'][k]['point'] for k in keys]); b=np.array([td['feet'][k]['point'] for k in keys])
    scale=np.ones(3);offset=np.zeros(3)
    for axis in [0,1]:
        scale[axis]=np.dot(a[:,axis]-a[:,axis].mean(), b[:,axis]-b[:,axis].mean())/np.sum((a[:,axis]-a[:,axis].mean())**2)
        offset[axis]=b[:,axis].mean()-scale[axis]*a[:,axis].mean()
    scale[2]=(td['merge']-b[:,2].mean())/(sd['merge']-a[:,2].mean())
    offset[2]=b[:,2].mean()-scale[2]*a[:,2].mean()
    if (scale<=0).any():raise ValueError('Invalid standard standing alignment')
    initial=sm['v']*scale+offset
    source_weights=source['weights'][sm['original_ids']]
    names=inventory['source']['vertex_groups']
    group_parts=np.array([PARTS.index(bone_part(n)) for n in names])
    pscores=np.stack([source_weights[:,group_parts==i].sum(1) for i in range(len(PARTS))],axis=1)
    slabel=pscores.argmax(1)
    # Source semantic labels are transferred by intrinsic descriptors, not xyz proximity.
    fd,fi=cKDTree(sd['features']).query(td['features'],k=5)
    weighted=1/np.maximum(fd,.01)**2; weighted/=weighted.sum(1,keepdims=True)
    tscores=np.sum(pscores[fi]*weighted[:,:,None],axis=1)
    tlabel=tscores.argmax(1)
    # Hard terminal groups are obtained by topology, not hand painted target regions.
    for k in keys:tlabel[td['feet'][k]['group']]=PARTS.index(k)
    tlabel[td['nose_candidate']]=PARTS.index('head');tlabel[td['tail_candidate']]=PARTS.index('tail')
    # Reject missing or implausibly small semantic regions; no silent nearest fallback.
    counts=np.bincount(tlabel,minlength=len(PARTS))
    if (counts<8).any():raise ValueError(f'Insufficient target part coverage: {counts}')
    adjacency=sm['g'].copy();adjacency.data[:]=1
    degree=np.asarray(adjacency.sum(1)).ravel()
    L=eye(len(initial))-diags(1/degree)@adjacency
    stiff=L.T@L
    x=initial.copy();steps=[]
    # Part-constrained, intrinsic-guided nearest samples; progressively allow local shape.
    tf=tm['f'];tflabel=np.array([np.bincount(tlabel[f],minlength=len(PARTS)).argmax() for f in tf])
    er,ec=adjacency.nonzero();edge_ref=initial[er]-initial[ec]
    for strength,intrinsic_weight in ([(4.,.6),(1.,.3),(.3,.15)] if args.arap else [(5.,.6),(1.,.3),(.2,.15)]):
        for iteration in range(10 if args.arap else 6):
            q=np.empty_like(x); correspondence=np.empty(len(x),int)
            for part in range(len(PARTS)):
                si=np.flatnonzero(slabel==part);ti=np.flatnonzero(tlabel==part)
                if args.arap:
                    face_ids=np.flatnonzero(tflabel==part)
                    augmented=np.c_[tm['v'],td['features']*intrinsic_weight]
                    face_index,bary,projected=closest_triangles(np.c_[x[si],sd['features'][si]*intrinsic_weight],augmented[tf[face_ids]])
                    q[si]=projected[:,:3]
                else:
                    tree=cKDTree(np.c_[tm['v'][ti],td['features'][ti]*intrinsic_weight])
                    distance,index=tree.query(np.c_[x[si],sd['features'][si]*intrinsic_weight])
                    correspondence[si]=ti[index];q[si]=tm['v'][ti[index]]
            confidence=np.ones(len(x))
            for si,ti in zip(sd['seeds'],td['seeds']):q[si]=tm['v'][ti];confidence[si]=20
            if args.arap:
                edge_now=x[er]-x[ec]
                covariance=np.zeros((len(x),3,3))
                np.add.at(covariance,er,edge_now[:,:,None]*edge_ref[:,None,:])
                U,S,Vh=np.linalg.svd(covariance);sign=np.ones((len(x),3));sign[:,2]=np.linalg.det(U@Vh)
                R=(U*sign[:,None,:])@Vh
                desired=np.einsum('nij,nj->ni',.5*(R[er]+R[ec]),edge_ref)
                rhs=np.zeros_like(x);np.add.at(rhs,er,desired)
                A=diags(confidence)+strength*(diags(degree)-adjacency)
                proposal=spsolve(A,confidence[:,None]*q+strength*rhs)
            else:
                A=diags(confidence)+strength*stiff
                delta=spsolve(A,confidence[:,None]*(q-initial))
                proposal=initial+delta
            step=float(np.max(np.linalg.norm(proposal-x,axis=1)));x=proposal
            steps.append({'stiffness':strength,'intrinsic_weight':intrinsic_weight,'iteration':iteration,'max_step':step})
    # Map interior joints with local regularized affine surface displacements.
    all_source=s0*scale+offset
    displacement=x-initial
    joints={};surface_tree={p:cKDTree(initial[slabel==i]) for i,p in enumerate(PARTS)}
    for bone in inventory['source']['bones']:
        name=bone['name'];part=bone_part(name);idx=np.flatnonzero(slabel==PARTS.index(part))
        result={}
        for end in ['head','tail']:
            point=(C@np.array(bone[end]))*scale+offset
            if name=='root':result[end]=point.tolist();continue
            distance,near=surface_tree[part].query(point,k=min(32,len(idx)))
            ids=idx[np.atleast_1d(near)]
            radius=max(float(np.max(distance)),.01*tm['span'])
            w=np.exp(-2*(np.atleast_1d(distance)/radius)**2)
            center=np.average(initial[ids],axis=0,weights=w)
            mu=np.average(displacement[ids],axis=0,weights=w)
            X=initial[ids]-center
            ridge=np.eye(3)*np.sum(w)*radius**2*.02
            gradient=np.linalg.solve(X.T@(w[:,None]*X)+ridge,X.T@(w[:,None]*(displacement[ids]-mu)))
            result[end]=(point+mu+(point-center)@gradient).tolist()
        result['part']=part;joints[name]=result
    wrapped_all=all_source.copy();wrapped_all[sm['original_ids']]=x
    # Detached eye geometry is excluded from transfer: target has no separate eye parts.
    target_labels=tlabel[tm['render_to_welded']]
    if (tm['render_to_welded']<0).any():raise ValueError('Target contains disconnected render geometry')
    dist=cKDTree(tm['v']).query(x)[0]
    before=np.linalg.norm(np.cross(initial[sm['f'][:,1]]-initial[sm['f'][:,0]],initial[sm['f'][:,2]]-initial[sm['f'][:,0]]),axis=1)
    after=np.linalg.norm(np.cross(x[sm['f'][:,1]]-x[sm['f'][:,0]],x[sm['f'][:,2]]-x[sm['f'][:,0]]),axis=1)
    summary={
        'case':args.case,'method':'part_guided_continuous_surface_ARAP' if args.arap else 'part_guided_sample_displacement_laplacian','parts':PARTS,'scale':scale.tolist(),'offset':offset.tolist(),
        'target_vertices_npz':str(Path(args.target_npz).resolve()) if args.target_npz else str(OLD/'inventory/target-mesh.npz'),
        'source_part_counts':dict(zip(PARTS,np.bincount(slabel,minlength=len(PARTS)).tolist())),
        'target_part_counts':dict(zip(PARTS,counts.tolist())),
        'source_seeds':{k:sm['v'][i].tolist() for k,i in zip(keys+['nose','tail'],sd['seeds'])},
        'target_seeds':{k:tm['v'][i].tolist() for k,i in zip(keys+['nose','tail'],td['seeds'])},
        'source_excluded_components_vertices':sm['excluded_vertices'],
        'surface_sample_distance_quantiles':np.quantile(dist,[.5,.95,1]).tolist(),
        'wrapped_faces_area_below_10pct':int((after/np.maximum(before,1e-10)<.1).sum()),
        'joints':joints,'iterations':steps,'body_merge_height':td['merge'],
        'limits':['Geodesic semantics and extrema are heuristics; visual/ambiguity review required.',
                  'Nearest target vertices are a fit diagnostic, not continuous surface distance.',
                  'Interior affine joint mapping does not prove anatomical centers.',
                  'Bone rest axes remain source canonical axes; tail pose/contact still unvalidated.'],
        'new_cat_automation_proven':False,
    }
    (out/'fit.json').write_text(json.dumps(summary,indent=2)+'\n')
    np.savez_compressed(out/'fit.npz',source_initial=initial,source_wrapped=x,source_triangles=sm['f'],
                        source_weights=source_weights,source_labels=slabel,
                        target_vertices=t0,target_triangles=target['triangles'],target_labels=target_labels,
                        target_welded=tm['v'],target_welded_labels=tlabel,
                        target_features=td['features'])
    print(json.dumps({k:summary[k] for k in ['case','target_part_counts','target_seeds','surface_sample_distance_quantiles','wrapped_faces_area_below_10pct']}),flush=True)


if __name__=='__main__':main()
