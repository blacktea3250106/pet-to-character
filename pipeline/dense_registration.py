"""Image-based local alignment without landmarks. A measurement candidate, not an identity judge.

Consumes already roughly aligned same-size normal-camera images and foreground masks.
The evaluator is separate so no annotated point can influence the flow estimate.
"""
import argparse,hashlib,json,time,sys,importlib.metadata
from pathlib import Path
import cv2,numpy as np
from PIL import Image

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for arg in ['render','reference','render-mask','reference-mask','out']:ap.add_argument('--'+arg,type=Path,required=True)
    ap.add_argument('--boundary-assist',action='store_true',help='Experimental mask-distance flow near silhouette, then smooth displacement; no landmark input')
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    # Preserve the executed version before processing, rather than only its later hash.
    executed_source=Path(__file__).read_bytes()
    (args.out/'estimator-source.py').write_bytes(executed_source)
    start=time.monotonic();cv2.setNumThreads(1);cv2.setRNGSeed(3101)
    a=np.asarray(Image.open(args.render).convert('RGB'));b=np.asarray(Image.open(args.reference).convert('RGB'))
    am=np.asarray(Image.open(args.render_mask).convert('L'))>127;bm=np.asarray(Image.open(args.reference_mask).convert('L'))>127
    assert a.shape==b.shape and a.shape[:2]==am.shape==bm.shape
    H,W=am.shape
    def gray(im,mask):
        result=cv2.cvtColor(im,cv2.COLOR_RGB2GRAY)
        result=cv2.GaussianBlur(result,(5,5),1.1)
        result[~mask]=190
        return np.ascontiguousarray(result)
    ga,gb=gray(a,am),gray(b,bm)
    def estimate(x,y):
        dis=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        dis.setFinestScale(0);dis.setUseMeanNormalization(True);dis.setUseSpatialPropagation(True)
        return dis.calc(x,y,None)
    forward=estimate(ga,gb);backward=estimate(gb,ga)
    if args.boundary_assist:
        def signed_distance(mask):
            inside=cv2.distanceTransform(mask.astype('uint8'),cv2.DIST_L2,5)
            outside=cv2.distanceTransform((~mask).astype('uint8'),cv2.DIST_L2,5)
            return np.uint8(np.clip(128+(inside-outside)*4,0,255)),inside
        sa,da=signed_distance(am);sb,db=signed_distance(bm)
        mf=estimate(sa,sb);mb=estimate(sb,sa)
        wa=np.clip(1-da/40,0,1)[...,None];wb=np.clip(1-db/40,0,1)[...,None]
        forward=cv2.GaussianBlur(forward*(1-wa)+mf*wa,(0,0),5)
        backward=cv2.GaussianBlur(backward*(1-wb)+mb*wb,(0,0),5)
    yy,xx=np.mgrid[:H,:W].astype(np.float32);sx=xx+forward[...,0];sy=yy+forward[...,1]
    reverse=cv2.remap(backward,sx,sy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(1e4,1e4))
    fb_error=np.linalg.norm(forward+reverse,axis=-1)
    dxx=np.gradient(forward[...,0],axis=1);dxy=np.gradient(forward[...,0],axis=0)
    dyx=np.gradient(forward[...,1],axis=1);dyy=np.gradient(forward[...,1],axis=0)
    determinant=(1+dxx)*(1+dyy)-dxy*dyx
    source_inside=cv2.remap(bm.astype(np.uint8),sx,sy,cv2.INTER_NEAREST)>0
    trusted=am&source_inside&(fb_error<=3)&(determinant>.1)&(determinant<8)&(np.linalg.norm(forward,axis=-1)<W*.1)
    warped=cv2.remap(b,sx,sy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(190,190,190))
    Image.fromarray(warped).save(args.out/'warped-reference-diagnostic.png')
    Image.fromarray(np.uint8(trusted)*255).save(args.out/'confidence.png')
    Image.fromarray(np.uint8(np.clip(fb_error/10,0,1)*255)).save(args.out/'forward-backward-error.png')
    np.savez_compressed(args.out/'flow.npz',forward=forward,backward=backward,fb_error=fb_error,jacobian=determinant,trusted=trusted)
    report={'method':'OpenCV DIS medium optical flow, finest scale 0, bidirectional consistency',
      'opencv':cv2.__version__,'reference_documentation':'https://docs.opencv.org/5.0/main_modules/classcv_1_1DISOpticalFlow.html',
      'python':sys.version,'packages':{k:importlib.metadata.version(k) for k in ['numpy','pillow','opencv-python-headless']},
      'input_hashes':{k:digest(getattr(args,k)) for k in ['render','reference','render_mask','reference_mask']},
      'script_hash':hashlib.sha256(executed_source).hexdigest(),'shape':[H,W],'landmarks_used_for_estimation':0,
      'settings':{'gray_gaussian_sigma':1.1,'background_gray':190,'fb_error_limit_px':3,'jacobian_range':[.1,8],'max_flow_fraction_width':.1,'rng_seed':3101,'threads':1},
      'elapsed_seconds':time.monotonic()-start,'trusted_fraction_of_render_mask':float(trusted[am].mean()),
      'nonpositive_jacobian_fraction_of_render_mask':float((determinant[am]<=0).mean()),
      'fb_error_render_mask_median_px':float(np.median(fb_error[am])),
      'identity_pass':None,'art_pass':None,'new_cat_automation_pass':False,
      'limitations':['Requires rough global camera alignment and masks supplied separately','Optical consistency does not establish semantic identity','Single-case experiment; repeated stripes can match the wrong stripe','No 3D asset altered by this command']}
    report['settings']['boundary_assist']=args.boundary_assist
    if args.boundary_assist:report['settings'].update({'boundary_blend_width_px':40,'distance_image_multiplier':4,'flow_gaussian_sigma':5})
    (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
