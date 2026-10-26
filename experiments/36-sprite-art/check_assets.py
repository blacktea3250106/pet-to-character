from pathlib import Path
from PIL import Image
import numpy as np,json,hashlib
p=Path(__file__).resolve().parent
files=['../33-sprite-static/godot/assets/cat-cutout-v001.png','candidate-v001.png','godot/assets/cat-art-v002.png']
results=[];masks=[]
for f in files:
 im=Image.open(p/f);a=np.asarray(im.getchannel('A'));m=a>=128;y,x=np.where(m);masks.append(m)
 results.append({'file':f,'size':list(im.size),'alpha_bbox_128':[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)],'opaque_border_pixels':int(m[0].sum()+m[-1].sum()+m[:,0].sum()+m[:,-1].sum()),'fully_transparent_fraction':float((a==0).mean()),'sha256':hashlib.sha256((p/f).read_bytes()).hexdigest()})
for i in [1,2]:
 if masks[i].shape==masks[0].shape:results[i]['silhouette_iou_vs_baseline']=float((masks[i]&masks[0]).sum()/(masks[i]|masks[0]).sum())
snapshot=json.loads((p.parent/'33-sprite-static/source-snapshot.json').read_text());changed=[]
for f,h in snapshot['catworld_godot_files'].items():
 if hashlib.sha256((Path('<catworld>/godot')/f).read_bytes()).hexdigest()!=h:changed.append(f)
out={'assets':results,'catworld_changed_files':changed,'note':'alpha IoU measures registration only, not identity or visual quality.'}
(p/'asset-check.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
