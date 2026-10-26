"""Measure source/candidate silhouette and RGB differences; never an art/identity score."""
import argparse,json,math,hashlib
from pathlib import Path
import cv2,numpy as np
from PIL import Image

def silhouette(mesh,view,size):
    _,az,el,target,scale=view;w,h=size;a,e=map(math.radians,[az,el])
    direction=np.array([math.cos(a)*math.cos(e),math.sin(a)*math.cos(e),math.sin(e)])
    right=np.array([-math.sin(a),math.cos(a),0]);up=np.cross(direction,right)
    points=mesh['verts']-np.array(target)
    xy=np.column_stack([w/2+points@right*w/scale,h/2-points@up*w/scale])
    mask=np.zeros((h,w),np.uint8)
    for tri in mesh['tris']:cv2.fillConvexPoly(mask,np.round(xy[tri]*16).astype(np.int32),1,shift=4)
    return mask.astype(bool)

def compare(baseline,candidate):
    a=np.load(baseline/'mesh.npz');b=np.load(candidate/'mesh.npz')
    report=json.loads((candidate/'render-report.json').read_text());out={}
    for view in report['views']:
        name=view[0];ia=Image.open(baseline/(name+'.png')).convert('RGB');ib=Image.open(candidate/(name+'.png')).convert('RGB');assert ia.size==ib.size
        ma=silhouette(a,view,ia.size);mb=silhouette(b,view,ib.size);both=ma&mb
        diff=np.abs(np.asarray(ia).astype(float)-np.asarray(ib).astype(float));pixels=diff[both]
        out[name]={'silhouette_iou':float(both.sum()/(ma|mb).sum()),'compared_cat_pixels':int(both.sum()),
            'mean_absolute_rgb_difference_255':float(pixels.mean()),'p95_per_pixel_mean_rgb_difference_255':float(np.percentile(pixels.mean(1),95))}
    return {'baseline':str(baseline),'candidate':str(candidate),'views':out,
        'interpretation':'Image-space change from the source under identical presentation, measured only on intersection of projected cat silhouettes. Includes geometry/lighting/material/texture differences, not pure albedo error.',
        'identity_or_art_pass':False,'camera_assumption':'Saved orthographic views with identical resolution and pixel aspect; raster projection convention previously checked against Blender.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('baseline',type=Path);parser.add_argument('output',type=Path);parser.add_argument('candidates',type=Path,nargs='+');args=parser.parse_args()
    data={'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'comparisons':[compare(args.baseline,p) for p in args.candidates]}
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    for c in data['comparisons']:print(c['candidate'],json.dumps(c['views']))
