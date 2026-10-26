"""Deterministic landmark-aligned projection onto the actual mesh UVs; no generative UV editing."""
import json, hashlib
from pathlib import Path
import numpy as np, cv2
from scipy.spatial import Delaunay
from scipy import ndimage
from PIL import Image, ImageDraw
from registration_probe import frame, raster
from surface_raster import raster_tris, zbuffer

P=Path(__file__).resolve().parent;OUT=P/'10-style-recovery'/'local-projection';OUT.mkdir(exist_ok=True)
lm=json.loads((P/'local_landmarks.json').read_text())
a=np.array([i[1] for i in lm['landmarks']],float);b=np.array([i[2] for i in lm['landmarks']],float)
# Identity background anchors bound interpolation, never supply fur evidence.
corners=np.array([[0,0],[1535,0],[1535,1023],[0,1023]],float)
a=np.vstack([a,corners]);b=np.vstack([b,corners]);delaunay=Delaunay(a)

def warp(q):
    idx=delaunay.find_simplex(q);safe=np.maximum(idx,0)
    uv=np.einsum('nij,nj->ni',delaunay.transform[safe,:2,:],q-delaunay.transform[safe,2,:])
    weights=np.column_stack([uv,1-uv.sum(1)])
    mapped=np.einsum('ni,nij->nj',weights,b[delaunay.simplices[safe]])
    mapped[idx<0]=np.nan
    return mapped

def area(tri):
    x=tri[:,1]-tri[:,0];y=tri[:,2]-tri[:,0]
    return x[:,0]*y[:,1]-x[:,1]*y[:,0]

ratios=area(b[delaunay.simplices])/area(a[delaunay.simplices])
hold=lm['holdout_landmarks'];pred=warp(np.array([i[1] for i in hold],float))
errors=np.linalg.norm(pred-np.array([i[2] for i in hold]),axis=1)
report={'method':'manual landmarks + piecewise affine interpolation; source-camera z-buffer and surface facing checks',
        'automatic_registration':False,'source':lm['source_image'],'control_points':len(lm['landmarks']),
        'inverted_mapping_triangles':int((ratios<=0).sum()),'area_ratio_range':[float(ratios.min()),float(ratios.max())],
        'holdout_errors_px':dict(zip([i[0] for i in hold],errors.tolist())),
        'holdout_rms_px':float(np.sqrt(np.mean(errors**2))),
        'holdout_max_px':float(errors.max()),'geometry_modified':False,
        'art_or_identity_pass':False,'limitations':lm['limitations']+['Source shading is not a recovered illumination-free albedo.','Geometric silhouette mismatch remains; this experiment aligns surface color only.']}
(OUT/'registration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False),flush=True)
if (ratios<=0).any() or errors.max()>15:
    raise RuntimeError('Local alignment gate failed; inspect annotations, do not bake')

src=np.asarray(Image.open(P/lm['source_image']).convert('RGB'));H,W=src.shape[:2]
yy,xx=np.mgrid[:H,:W];q=warp(np.column_stack([xx.ravel()+.5,yy.ravel()+.5])).reshape(H,W,2)
preview=cv2.remap(src,q[...,0].astype('float32'),q[...,1].astype('float32'),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(190,190,190))
Image.fromarray(preview).save(OUT/'warped-reference-diagnostic.png')
im=Image.fromarray(preview.copy());draw=ImageDraw.Draw(im)
for i,(name,xy,_) in enumerate(lm['landmarks']):
    x,y=xy;draw.ellipse((x-3,y-3,x+3,y+3),fill='#00ffcc');draw.text((x+4,y),str(i),fill='#ff0055',stroke_width=1,stroke_fill='white')
im.save(OUT/'landmark-review.png')

mesh=P/'10-style-recovery/clean-flat/mesh.npz';m=np.load(mesh);v,t,uv=m['verts'],m['tris'],m['tri_uv']
params=json.loads((P/'10-style-recovery/registration/camera.json').read_text())['params']
s,tx,ty,az,el=params;r,u,d=frame(az,el)
project=lambda pts:np.column_stack([s*(pts@r)+tx,-s*(pts@u)+ty])
S=2048
cov,pos,tid=raster_tris(np.stack([uv[...,0]*S,(1-uv[...,1])*S],-1),(S,S),v[t])
pts=pos[cov];ids=tid[cov];pq=project(pts);sourceq=warp(pq)
zb=zbuffer(project(v),v@d,t,(H,W))
px=np.floor(pq[:,0]).astype(int);py=np.floor(pq[:,1]).astype(int)
safe=(px>=0)&(px<W)&(py>=0)&(py<H)&np.isfinite(sourceq).all(1)
visible=np.zeros(len(pts),bool);visible[safe]=pts[safe]@d>=zb[py[safe],px[safe]]-.0015
normal=np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]])
normal/=np.maximum(np.linalg.norm(normal,axis=1,keepdims=True),1e-12)
facing=np.clip(normal[ids]@d,0,1)
gc=np.zeros((H,W),np.uint8)
cv2.grabCut(src,gc,(8,8,W-16,H-16),np.zeros((1,65)),np.zeros((1,65)),4,cv2.GC_INIT_WITH_RECT)
source_mask=np.isin(gc,[1,3]);distance=ndimage.distance_transform_edt(source_mask)
sq=np.nan_to_num(sourceq,nan=-100).astype(np.float32)
source_distance=cv2.remap(distance.astype(np.float32),sq[:,0].reshape(-1,1),sq[:,1].reshape(-1,1),cv2.INTER_LINEAR)[:,0] if len(sq)<32767 else ndimage.map_coordinates(distance,[sq[:,1]-.5,sq[:,0]-.5],order=1,mode='constant',cval=0)
# Fade only at genuinely unobserved/grazing surface boundaries, not across facial labels.
weight=visible*np.clip((facing-.12)/.3,0,1)*np.clip((source_distance-2)/6,0,1)
sample=np.stack([ndimage.map_coordinates(src[...,k].astype(float),[sq[:,1]-.5,sq[:,0]-.5],order=1,mode='constant',cval=0) for k in range(3)],1)/255
base=np.asarray(Image.open(next((P/'06c-raw-single').glob('material-*.png'))).convert('RGB')).astype(float)/255
linear=lambda x:np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
srgb=lambda x:np.where(x<=.0031308,12.92*x,1.055*np.maximum(x,0)**(1/2.4)-.055)
result=base.copy();result[cov]=srgb(linear(sample)*weight[:,None]+linear(base[cov])*(1-weight[:,None]))
dist,nearest=ndimage.distance_transform_edt(~cov,return_indices=True);pad=(~cov)&(dist<=16)
result[pad]=result[nearest[0][pad],nearest[1][pad]]
Image.fromarray(np.uint8(np.clip(result,0,1)*255)).save(OUT/'local-color.png')
confidence=np.zeros((S,S),np.float32);confidence[cov]=weight
Image.fromarray(np.uint8(confidence*255)).save(OUT/'projection-confidence.png')
np.savez_compressed(OUT/'surface-correspondence.npz',tri_id=tid,pos=pos,coverage=cov,weight=confidence,source_xy=sourceq.astype(np.float32))
report.update({'mesh_sha256':hashlib.sha256(mesh.read_bytes()).hexdigest(),'triangles':len(t),'atlas_size':[S,S],
    'fraction_covered_texels_receiving_projection':float((weight>.01).mean()),
    'fraction_covered_texels_with_full_projection':float((weight>.99).mean()),
    'unseen_policy':'retain native Tripo texture and zero source confidence; no symmetry or invented observation',
    'manual_render_review_pending':True})
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('LOCAL_PROJECTION_COMPLETE',report['fraction_covered_texels_receiving_projection'],flush=True)
