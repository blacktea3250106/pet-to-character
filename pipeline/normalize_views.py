"""Reviewed crop/landmark normalization, never independent bbox filling."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image,ImageDraw
P=Path(__file__).resolve().parent/'04-views'
im=np.array(Image.open(P/'turnaround-v2.png').convert('RGB'))
# Coordinates were reviewed on this particular 1254-square generated sheet.
# Global source crop, ear-tip height, ground height: rigid scale/translation only.
spec={'front':([40,20,420,570],80,541), 'left':([530,25,1230,565],118,537),
      'back':([100,590,425,1185],676,1156),'right':([490,610,1230,1180],700,1150)}
sheet=Image.new('RGB',(2048,2048),(224,224,224));report={}
for n,(view,(box,ear,ground)) in enumerate(spec.items()):
 x0,y0,x1,y1=box;a=im[y0:y1,x0:x1].copy();h,w=a.shape[:2]
 gc=np.zeros((h,w),np.uint8)
 cv2.grabCut(a,gc,(4,4,w-8,h-8),np.zeros((1,65)),np.zeros((1,65)),5,cv2.GC_INIT_WITH_RECT)
 m=np.isin(gc,[1,3]).astype(np.uint8)
 num,lab,stats,cent=cv2.connectedComponentsWithStats(m)
 if num>1:m=(lab==(1+np.argmax(stats[1:,cv2.CC_STAT_AREA]))).astype(np.uint8)
 scale=600/(ground-ear)
 ys,xs=np.where(m)
 tx=512-scale*(float(xs.min()+xs.max())/2)
 ty=880-scale*(ground-y0)
 M=np.array([[scale,0,tx],[0,scale,ty]],np.float32)
 bg=np.full((1024,1024,3),224,np.uint8)
 warped=cv2.warpAffine(a,M,(1024,1024),flags=cv2.INTER_LANCZOS4,borderValue=(224,224,224))
 wm=cv2.warpAffine(m,M,(1024,1024),flags=cv2.INTER_NEAREST)
 result=np.where(wm[...,None]>0,warped,bg)
 Image.fromarray(result).save(P/f'{view}.png');Image.fromarray(wm*255).save(P/f'{view}-mask.png')
 sheet.paste(Image.fromarray(result),((n%2)*1024,(n//2)*1024))
 report[view]={'crop':box,'source_ear_y':ear,'source_ground_y':ground,'uniform_scale':scale,'target_ear_y':280,'target_ground_y':880,'native_crop_size':[w,h],'upscaled':scale>1,'matrix':M.tolist()}
sheet.resize((1400,1400)).save(P/'normalized-four-views.jpg')
(P/'normalization.json').write_text(json.dumps({'method':'reviewed ear-to-ground shared scale; no anisotropic warp; no native-detail claim from upscaling','views':report},indent=2))
print(json.dumps(report))
