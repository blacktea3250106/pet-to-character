"""Visibility-checked single-reference projection, body facet colors, feature exceptions."""
from pathlib import Path
import json,math
import numpy as np
import cv2
from PIL import Image
from scipy import optimize,ndimage
from surface_raster import raster_tris,zbuffer

P=Path(__file__).resolve().parent;OUT=P/'08b-coat';OUT.mkdir(exist_ok=True)
def linear(x):return np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
def srgb(x):return np.where(x<=.0031308,12.92*x,1.055*np.maximum(x,0)**(1/2.4)-.055)
def frame(az,el):
 a,e=np.deg2rad([az,el]);d=np.array([np.cos(a)*np.cos(e),np.sin(a)*np.cos(e),np.sin(e)])
 r=np.array([-np.sin(a),np.cos(a),0]);u=np.cross(d,r);return r,u,d
def project(v,p):
 s,tx,ty,az,el=p;r,u,d=frame(az,el);return np.stack([s*(v@r)+tx,-s*(v@u)+ty],1)

d=np.load(P/'07b-geometry/mesh.npz');v,t,uv=d['verts'],d['tris'],d['tri_uv']
source=np.array(Image.open(P/'04b-single-reference/standing.png').convert('RGB'));H,W=source.shape[:2]
gc=np.zeros((H,W),np.uint8);cv2.grabCut(source,gc,(8,8,W-16,H-16),np.zeros((1,65)),np.zeros((1,65)),4,cv2.GC_INIT_WITH_RECT)
mask=np.isin(gc,[1,3]).astype(np.uint8);Image.fromarray(mask*255).save(OUT/'reference-mask.png')
low=160;ratio=low/W;lh=round(H*ratio);small=cv2.resize(mask,(low,lh),interpolation=cv2.INTER_NEAREST)>0
def loss(p):
 s,tx,ty,az,el=p
 if s<=0 or not(-75<az<0 and 0<el<35):return 2
 q=np.round(project(v,p)*ratio).astype(np.int32)
 render=np.zeros((lh,low),np.uint8)
 for triangle in q[t]:cv2.fillConvexPoly(render,triangle,1)
 render=render>0
 return 1-(render&small).sum()/max((render|small).sum(),1)
r,u,_=frame(-38,10);a,b=v@r,v@u;ys,xs=np.where(mask)
s=min((xs.max()-xs.min())/np.ptp(a),(ys.max()-ys.min())/np.ptp(b))
p0=[s,(xs.min()+xs.max())/2-s*(a.min()+a.max())/2,(ys.min()+ys.max())/2+s*(b.min()+b.max())/2,-38,10]
fit=optimize.minimize(loss,p0,method='Nelder-Mead',options={'maxiter':180,'xatol':.02,'fatol':1e-5})
params=fit.x;iou=1-loss(params);print('camera_iou',round(iou,4),'params',params.tolist(),flush=True)
q=project(v,params);sil=np.zeros((H,W),np.uint8)
for triangle in np.round(q[t]).astype(np.int32):cv2.fillConvexPoly(sil,triangle,1)
edge=cv2.morphologyEx(sil,cv2.MORPH_GRADIENT,np.ones((3,3),np.uint8))>0
overlay=source.copy();overlay[edge]=[0,220,160];Image.fromarray(overlay).save(OUT/'registration-overlay.png')

S=2048
texpath=next((P/'06c-raw-single').glob('material-*.png'))
base=np.array(Image.open(texpath).convert('RGB').resize((S,S)))/255.;base=linear(base)
uvpix=np.stack([uv[...,0]*S,(1-uv[...,1])*S],-1)
cov,pos,tid=raster_tris(uvpix,(S,S),v[t]);print('rasterized',int(cov.sum()),flush=True)
n=np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]]);n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-12)
pts=pos[cov];ids=tid[cov];r,u,direction=frame(params[3],params[4])
zb=zbuffer(q,v@direction,t,(H,W));pq=project(pts,params)
px=np.floor(pq[:,0]).astype(int);py=np.floor(pq[:,1]).astype(int)
ok=(px>=0)&(px<W)&(py>=0)&(py<H)
inner=ndimage.binary_erosion(mask,iterations=3)
ok[ok]&=inner[py[ok],px[ok]]&(pts[ok]@direction>=zb[py[ok],px[ok]]-.0052)
facing=np.clip(n[ids]@direction,0,1)**4
head=(pts[:,0]>.17)&(pts[:,2]>.21)
# Local face registration is not yet validated: protect reviewed native facial details.
projected=ok&(facing>.18)&~head&(iou>=.85)
colors=base[cov].copy();colors[projected]=linear(source[py[projected],px[projected]]/255.)
working=base.copy();working[cov]=colors
coverage=np.zeros((S,S),np.uint8);coverage[cov]=projected*255;Image.fromarray(coverage).save(OUT/'reference-coverage.png')
headmap=np.zeros((S,S),np.uint8);headmap[cov]=head*255;Image.fromarray(headmap).save(OUT/'protected-face-mask.png')
Image.fromarray(np.uint8(np.clip(srgb(working),0,1)*255)).save(OUT/'projected-color.png')

# Classify only to guard boundaries; shades within one class remain continuous.
display=np.float32(np.clip(srgb(colors),0,1));lab=cv2.cvtColor(display.reshape(-1,1,3),cv2.COLOR_RGB2Lab).reshape(-1,3)
labels=np.full(len(lab),3,np.int32)
labels[lab[:,0]<36]=0
labels[(lab[:,2]>12)&(lab[:,0]>=36)]=1
labels[(lab[:,0]>=55)&(np.linalg.norm(lab[:,1:],axis=1)<20)]=2
F=len(t);cnt=np.bincount(ids,minlength=F)
means=np.stack([np.bincount(ids,weights=colors[:,k],minlength=F) for k in range(3)],1)/np.maximum(cnt[:,None],1)
hist=np.stack([np.bincount(ids,weights=labels==k,minlength=F) for k in range(4)],1)
pure=hist.max(1)/np.maximum(cnt,1)>.93
headfaces=np.bincount(ids,weights=head,minlength=F)>0
flatten=pure&~headfaces&(cnt>=3)
out=working.copy();result=colors.copy();f=flatten[ids];result[f]=means[ids[f]];out[cov]=result
# Bounded padding; atlas islands must still be checked under mipmapping in the viewer.
dist,nearest=ndimage.distance_transform_edt(~cov,return_indices=True)
pad=(~cov)&(dist<=16);out[pad]=out[nearest[0][pad],nearest[1][pad]]
Image.fromarray(np.uint8(np.clip(srgb(out),0,1)*255)).save(OUT/'facet-color.png')
np.savez_compressed(OUT/'surface-map.npz',pos=pos,tri_id=tid,coverage=cov)
report={'stage':'P08-P09 deterministic surface processing','camera':params.tolist(),'silhouette_iou_at_160px':float(iou),'projection_accepted_for_poc':bool(iou>=.85),'production_iou_review_trigger':.85,'source':'04b-single-reference/standing.png','atlas':[S,S],'reference_projected_fraction_of_covered_texels':float(projected.mean()),'head_policy':'native reviewed face retained; no unvalidated head projection','facet_averaged_faces':int(flatten.sum()),'total_faces':F,'boundary_or_feature_faces_preserved':int((~flatten).sum()),'color_space':'exact sRGB transfer; weighted means in linear space','palette_labels':'Lab threshold heuristic to protect black/orange/white transitions, not a learned fur detector','padding_px':16,'unseen_surface':'Tripo base retained, inferred; not original-photo observed evidence','automatic_quality_pass':False}
(OUT/'processing-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
