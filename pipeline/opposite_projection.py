"""Known-camera reference projection. Isolated candidate; never replaces the selected asset.

No hand-drawn correspondences. Camera/view and source evidence were manually selected.
Silhouette agreement is a diagnostic, not proof of semantic registration or identity.
"""
import argparse, hashlib, json, time
from pathlib import Path
import cv2
import numpy as np
from scipy import ndimage
from scipy.optimize import least_squares
from PIL import Image
from registration_probe import frame, raster
from surface_raster import raster_tris, zbuffer

P=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--bake',action='store_true')
parser.add_argument('--align',action='store_true')
parser.add_argument('--profile',type=Path)
args=parser.parse_args();started=time.monotonic()
cfg=json.loads(args.profile.read_text()) if args.profile else {}
OUT=P/cfg.get('output','11-other-side/'+('projection-v002' if args.align else 'projection-v001'))
OUT.mkdir(exist_ok=True)
executed_source=Path(__file__).read_bytes()
(OUT/'executed-source.py').write_bytes(executed_source)
source=P/cfg.get('source','11-other-side/reference-v001/reference.png')
mesh=P/cfg.get('mesh','10-style-recovery/eye-material/mesh.npz')
basefile=P/cfg.get('base_color','10-style-recovery/local-projection/local-color.png')
oldfiles=[P/p for p in cfg.get('prior_correspondences',['10-style-recovery/local-projection/surface-correspondence.npz'])]
H,W=cfg.get('size_hw',[900,1200])
src=np.asarray(Image.open(source).convert('RGB').resize((W,H),Image.Resampling.LANCZOS))
m=np.load(mesh);v,t,uv=m['verts'],m['tris'],m['tri_uv']
target=np.array(cfg.get('target',[0,0,.20]));scale=cfg.get('scale',.79);az,el=cfg.get('az_el',[110,10])
r,u,d=frame(az,el);s=W/scale
tx=W/2-s*(target@r);ty=H/2+s*(target@u)
params=[s,tx,ty,az,el]
project=lambda pts:np.column_stack([s*(pts@r)+tx,-s*(pts@u)+ty])
tid,_,_,_,zb=raster(v,t,uv,params,(H,W));mask=tid>=0
cv2.setRNGSeed(3103)
gc=np.zeros((H,W),np.uint8)
segmentation=cfg.get('segmentation','rectangle')
if segmentation=='render_prior':
    margin=cfg.get('segmentation_outer_margin_px',60)
    core=cfg.get('segmentation_inner_margin_px',25)
    outside_distance=ndimage.distance_transform_edt(~mask)
    inside_distance=ndimage.distance_transform_edt(mask)
    gc[:]=cv2.GC_PR_BGD;gc[mask]=cv2.GC_PR_FGD
    gc[outside_distance>margin]=cv2.GC_BGD
    gc[inside_distance>core]=cv2.GC_FGD
    cv2.grabCut(src,gc,None,np.zeros((1,65)),np.zeros((1,65)),5,cv2.GC_INIT_WITH_MASK)
else:
    assert segmentation=='rectangle'
    cv2.grabCut(src,gc,(8,8,W-16,H-16),np.zeros((1,65)),np.zeros((1,65)),5,cv2.GC_INIT_WITH_RECT)
source_mask=np.isin(gc,[1,3])
raw_iou=(mask&source_mask).sum()/max((mask|source_mask).sum(),1)
distance=ndimage.distance_transform_edt(source_mask)
alignment=np.array([1.,1.,0.,0.])
center=np.array([W/2,H/2])
map_source=lambda q:(q-center)*alignment[:2]+center+alignment[2:]
if args.align:
    def boundary_points(m):
        y,x=np.where(m^ndimage.binary_erosion(m))
        step=max(1,len(x)//2000)
        return np.column_stack([x[::step]+.5,y[::step]+.5])
    rp,sp=boundary_points(mask),boundary_points(source_mask)
    rsdf=ndimage.distance_transform_edt(mask)-ndimage.distance_transform_edt(~mask)
    ssdf=distance-ndimage.distance_transform_edt(~source_mask)
    def residual(p):
        forward=(rp-center)*p[:2]+center+p[2:]
        inverse=(sp-center-p[2:])/p[:2]+center
        return np.r_[ndimage.map_coordinates(ssdf,[forward[:,1]-.5,forward[:,0]-.5],order=1,mode='constant',cval=-200),ndimage.map_coordinates(rsdf,[inverse[:,1]-.5,inverse[:,0]-.5],order=1,mode='constant',cval=-200)]
    fit=least_squares(residual,alignment,bounds=([.8,.8,-120,-90],[1.2,1.2,120,90]),loss='soft_l1',f_scale=8,max_nfev=100)
    alignment=fit.x
yy,xx=np.mgrid[:H,:W];mapped=map_source(np.column_stack([xx.ravel()+.5,yy.ravel()+.5]))
coords=[mapped[:,1]-.5,mapped[:,0]-.5]
warped_mask=ndimage.map_coordinates(source_mask.astype(np.uint8),coords,order=0,mode='constant',cval=0).reshape(H,W).astype(bool)
iou=(mask&warped_mask).sum()/max((mask|warped_mask).sum(),1)
warped=np.stack([ndimage.map_coordinates(src[...,k],coords,order=1,mode='constant',cval=190).reshape(H,W) for k in range(3)],-1)
edge=mask^ndimage.binary_erosion(mask)
overlay=warped.copy();overlay[edge]=[255,0,180]
Image.fromarray(overlay).save(OUT/'silhouette-overlay.png')
Image.fromarray(np.uint8(mask)*255).save(OUT/'render-mask.png')
Image.fromarray(np.uint8(source_mask)*255).save(OUT/'source-mask.png')
Image.fromarray(src).save(OUT/'normalized-reference.png')
Image.fromarray(warped).save(OUT/'aligned-reference-diagnostic.png')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report={
 'method':'known orthographic render camera; resolution normalization; GrabCut source mask; visibility/facing and source-edge margin; preserve prior-view confidence',
 'inputs':[{'path':str(p.relative_to(P)),'sha256':sha(p)} for p in [source,mesh,basefile,*oldfiles]],
 'profile':cfg,'profile_sha256':sha(args.profile) if args.profile else None,
 'script_sha256':hashlib.sha256(executed_source).hexdigest(),
 'camera':{'params':params,'size':[H,W],'target':target.tolist(),'orthographic_scale':scale},
 'source_original_size':list(Image.open(source).size),
 'silhouette_iou':float(iou),
 'unaligned_silhouette_iou':float(raw_iou),
 'alignment':{'method':'bounded symmetric silhouette-distance fit, scales and translation only' if args.align else 'identity','render_to_source_scale_xy_translation_xy':alignment.tolist(),'manual_landmarks':False},
 'reference_missed_render_fraction':float((mask&~warped_mask).sum()/mask.sum()),
 'reference_outside_render_fraction':float((warped_mask&~mask).sum()/warped_mask.sum()),
 'source_segmentation':{'method':'GrabCut '+segmentation,'iterations':5,'rng_seed':3103,'manual_mask':False,'conditioned_on_render_silhouette':segmentation=='render_prior','validation_limit':'A render prior can constrain the answer; IoU is not an independent pose validation.' if segmentation=='render_prior' else None},
 'manual_decisions':['selected source photos, anatomical interpretation, style prompt and render camera','visual reference acceptance remains human-reviewed'],
 'geometry_changed':False,'uv_changed':False,'rig_or_weights_changed':False,
 'production_automation_pass':False,'identity_or_art_pass':False,
 'limitations':['ImageGen can shift pose or shape despite an edit prompt.','Silhouette agreement does not validate interior semantic correspondences.','Color comes from an AI reference guided by photos; it is not directly observed albedo.','Unseen and rejected texels retain previous colors and their existing uncertainty.'],
 'bake_requested':args.bake,'adopted_as_selected_asset':False
}
(OUT/'diagnostic-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'iou':float(iou),'missed':report['reference_missed_render_fraction'],'extra':report['reference_outside_render_fraction']},ensure_ascii=False),flush=True)
if not args.bake:raise SystemExit(0)
if iou<.85:raise RuntimeError('Silhouette diagnostic failed; no texture written')
S=2048
cov,pos,atlas_tid=raster_tris(np.stack([uv[...,0]*S,(1-uv[...,1])*S],-1),(S,S),v[t])
pts=pos[cov];ids=atlas_tid[cov];pq=project(pts)
sq=map_source(pq)
px=np.floor(pq[:,0]).astype(int);py=np.floor(pq[:,1]).astype(int)
safe=(px>=0)&(px<W)&(py>=0)&(py<H)
visible=np.zeros(len(pts),bool);visible[safe]=pts[safe]@d>=zb[py[safe],px[safe]]-.0015
normals=np.cross(v[t[:,1]]-v[t[:,0]],v[t[:,2]]-v[t[:,0]])
normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
facing=np.clip(normals[ids]@d,0,1)
sample_at=lambda img:ndimage.map_coordinates(img,[sq[:,1]-.5,sq[:,0]-.5],order=1,mode='constant',cval=0)
edge_weight=np.clip((sample_at(distance)-8)/12,0,1)
prior_weights=[]
for oldfile in oldfiles:
    old=np.load(oldfile);assert np.array_equal(old['tri_id'],atlas_tid)
    prior_weights.append(old['weight'][cov])
old_weight=np.maximum.reduce(prior_weights)
prior_policy=cfg.get('prior_policy','one_minus_max')
if prior_policy=='protect_strong_replace_weak':
    low,high=cfg['prior_fade_range'];prior_allow=np.clip((high-old_weight)/(high-low),0,1)
    prior_allow=prior_allow*prior_allow*(3-2*prior_allow)
else:
    assert prior_policy=='one_minus_max';prior_allow=1-old_weight
surface_allow=np.ones(len(pts))
if 'world_up_normal_fade' in cfg:
    low,high=cfg['world_up_normal_fade'];surface_allow=np.clip((normals[ids,2]-low)/(high-low),0,1)
if 'case_body_x_window' in cfg:
    low,high,fade=cfg['case_body_x_window']
    surface_allow*=np.minimum(np.clip((pts[:,0]-low)/fade,0,1),np.clip((high-pts[:,0])/fade,0,1))
    report['manual_decisions'].append('Case-specific body x-window excludes the head and tail; not an automatic semantic body segmentation.')
weight=visible*np.clip((facing-.18)/.35,0,1)*edge_weight*prior_allow*surface_allow
sample=np.stack([sample_at(src[...,k].astype(float)) for k in range(3)],1)/255
base=np.asarray(Image.open(basefile).convert('RGB')).astype(float)/255
linear=lambda x:np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
srgb=lambda x:np.where(x<=.0031308,12.92*x,1.055*np.maximum(x,0)**(1/2.4)-.055)
result=base.copy();result[cov]=srgb(linear(sample)*weight[:,None]+linear(base[cov])*(1-weight[:,None]))
dist,nearest=ndimage.distance_transform_edt(~cov,return_indices=True);pad=(~cov)&(dist<=16)
result[pad]=result[nearest[0][pad],nearest[1][pad]]
Image.fromarray(np.uint8(np.clip(result,0,1)*255)).save(OUT/'color.png')
confidence=np.zeros((S,S),np.float32);confidence[cov]=weight
Image.fromarray(np.uint8(confidence*255)).save(OUT/'new-view-weight.png')
np.savez_compressed(OUT/'surface-correspondence.npz',tri_id=atlas_tid,coverage=cov,weight=confidence,source_xy=sq.astype(np.float32))
protected=old_weight>=.99
report.update({
 'atlas_size':[S,S],'triangles':len(t),
 'fraction_covered_texels_receiving_new_reference':float((weight>.01).mean()),
 'fraction_covered_texels_with_strong_new_reference':float((weight>.9).mean()),
 'fraction_covered_texels_with_any_reference_old_or_new':float(((old_weight>.01)|(weight>.01)).mean()),
 'old_full_confidence_texels_affected_above_0_01_weight':int((protected&(weight>.01)).sum()),
 'settings':{'depth_tolerance_m':.0015,'facing_start':.18,'facing_full':.53,'source_edge_fade_px':[8,20],'prior_weight_policy':prior_policy,'prior_combination':'maximum algorithmic weight, not calibrated probability','padding_px':16},
 'elapsed_seconds':time.monotonic()-started,'manual_render_review_pending':True
})
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:report[k] for k in ['fraction_covered_texels_receiving_new_reference','fraction_covered_texels_with_any_reference_old_or_new','old_full_confidence_texels_affected_above_0_01_weight']}),flush=True)
