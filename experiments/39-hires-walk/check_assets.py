from pathlib import Path
from PIL import Image
import numpy as np,json
p=Path(__file__).resolve().parent
out=[]
for d in range(8):
 im=Image.open(p/f'godot/assets/walk-{d}.png');a=np.asarray(im.getchannel('A'));h,w=a.shape;frames=[]
 for f in range(4):
  x0=(f%2)*w//2;x1=((f%2)+1)*w//2;y0=(f//2)*h//2;y1=((f//2)+1)*h//2
  m=a[y0:y1,x0:x1]>=128;y,x=np.where(m)
  frames.append({'region':[x0,y0,x1-x0,y1-y0],'bbox':[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],'edge':int(m[0].sum()+m[-1].sum()+m[:,0].sum()+m[:,-1].sum()),'area':int(m.sum())})
 out.append({'direction':d,'size':[w,h],'frames':frames})
(p/'asset-check.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
