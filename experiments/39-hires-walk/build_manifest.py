from pathlib import Path
from PIL import Image
import numpy as np,json
from scipy import ndimage
p=Path(__file__).resolve().parent;directions=[]
for d in range(8):
 im=Image.open(p/f'godot/assets/walk-{d}.png');a=np.asarray(im.getchannel('A'));h,w=a.shape;frames=[]
 assert min(w,h)//2>=500
 for f in range(4):
  x0=f%2*w//2;x1=(f%2+1)*w//2;y0=f//2*h//2;y1=(f//2+1)*h//2
  m=a[y0:y1,x0:x1]>=128;labels,n=ndimage.label(m);counts=np.bincount(labels.ravel());counts[0]=0;body=labels==counts.argmax();ys,xs=np.where(body)
  box=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]
  band=body.copy();band[:int(box[1]+(box[3]-box[1])*.25)]=False;band[int(box[1]+(box[3]-box[1])*.75):]=False
  cy,cx=np.where(band)
  frames.append({'region':[x0,y0,x1-x0,y1-y0],'bbox':box,'pivot':[float(np.median(cx)),box[3]],'border_body_pixels':int(body[0].sum()+body[-1].sum()+body[:,0].sum()+body[:,-1].sum())})
 height=float(np.median([f['bbox'][3]-f['bbox'][1] for f in frames]));directions.append({'texture':f'res://assets/walk-{d}.png','pixel_size':.62/height,'frames':frames})
manifest={'directions':directions,'layout':'2x2','cycle_distance':.42,'frame_count':4,'registration':'largest alpha component, body-band median x and bottommost silhouette y; shared rule, not anatomical paw detection','world_height':.62,'rear_left_status':'initial candidate; requested correction interrupted by user; head still partially looks sideways'}
(p/'godot/animation.json').write_text(json.dumps(manifest,indent=2));print('32 frames, >=627px cells, native sources; border body pixels:',[sum(f['border_body_pixels'] for f in d['frames']) for d in directions])
