"""POC: reviewed silhouette seed + GrabCut; originals are never changed."""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

HERE=Path(__file__).resolve().parent
OUT=HERE/'01-segmentation'; OUT.mkdir(exist_ok=True)
im=np.asarray(Image.open(HERE/'00-input/photo-05.png').convert('RGB'))
# Explicit human/assistant-reviewed seed, in pixels of photo-05; not an automatic detector.
outline=[(0,486),(55,503),(112,531),(146,571),(177,584),(233,572),(302,566),(365,570),(431,596),(490,630),(535,677),(549,650),(528,606),(515,562),(562,588),(605,599),(672,597),(739,597),(813,600),(864,578),(947,557),(919,617),(878,666),(876,716),(867,759),(873,811),(893,857),(885,912),(878,940),(903,967),(918,997),(926,1033),(900,1054),(891,1081),(865,1104),(816,1100),(742,1092),(683,1088),(600,1077),(542,1056),(475,1061),(410,1057),(369,1045),(330,1056),(282,1041),(229,1033),(196,1015),(193,975),(195,920),(162,867),(139,803),(122,730),(104,667),(91,612),(50,576),(0,554)]
seed=np.zeros(im.shape[:2],np.uint8); cv2.fillPoly(seed,[np.array(outline,np.int32)],1)
kernel=np.ones((15,15),np.uint8)
er=cv2.erode(seed,kernel);di=cv2.dilate(seed,kernel)
gc=np.where(di,cv2.GC_PR_BGD,cv2.GC_BGD).astype(np.uint8)
gc[seed==1]=cv2.GC_PR_FGD; gc[er==1]=cv2.GC_FGD
cv2.grabCut(im,gc,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
mask=np.isin(gc,[cv2.GC_FGD,cv2.GC_PR_FGD])
Image.fromarray(mask.astype(np.uint8)*255).save(OUT/'mask.png')
rgba=np.dstack([im,mask.astype(np.uint8)*255]);Image.fromarray(rgba).save(OUT/'cutout.png')
clean=np.where(mask[...,None],im,224).astype(np.uint8)
Image.fromarray(clean).save(OUT/'isolated.png')
crop=(0,450,990,1140);Image.fromarray(clean).crop(crop).save(OUT/'identity-source.png')
overlay=im.copy(); edge=cv2.morphologyEx(mask.astype(np.uint8),cv2.MORPH_GRADIENT,np.ones((4,4),np.uint8)).astype(bool)
overlay[edge]=[0,220,160];Image.fromarray(overlay).save(OUT/'overlay.png')
sheet=Image.new('RGB',(1500,800),'#eeeeeb');dr=ImageDraw.Draw(sheet)
for i,(name,arr) in enumerate([('SOURCE',im),('REVIEWED MASK',overlay),('ISOLATED',clean)]):
 thumb=ImageOps.contain(Image.fromarray(arr),(490,740));sheet.paste(thumb,(i*500+(500-thumb.width)//2,40));dr.text((i*500+16,14),name,fill='black')
sheet.save(OUT/'comparison.jpg')
(OUT/'manifest.json').write_text(json.dumps({'method':'reviewed silhouette polygon + 3 iterations GrabCut','automatic_segmentation_claim':False,'source':'photo-05','outline':outline,'crop':crop,'limitations':['Tail tip is clipped in original; not reconstructed here.','Fine whiskers are not the target silhouette.','Other photos remain identity evidence, not projected full-body textures.']},indent=2))
features=[
 {'id':'face_right_orange','region':'anatomical right cheek / image left','source':['photo-04','photo-05'],'bbox_photo05':[588,703,718,863],'description':'Orange around eye/cheek, white lower muzzle.','evidence':'observed'},
 {'id':'face_left_black','region':'anatomical left cheek / image right','source':['photo-04','photo-05'],'bbox_photo05':[765,735,882,885],'description':'Large black cheek patch with warm orange/cream eyebrow.','evidence':'observed'},
 {'id':'nose_bridge','region':'central face','source':['photo-05'],'bbox_photo05':[710,740,788,889],'description':'Broad black nasal bridge.','evidence':'observed'},
 {'id':'nose_pink','region':'nose tip','source':['photo-05'],'bbox_photo05':[720,870,767,902],'description':'Small pink mottled patch on otherwise dark nose tip; not all-black or all-pink.','evidence':'observed'},
 {'id':'bib','region':'chest','source':['photo-04','photo-05','photo-06'],'bbox_photo05':[549,844,876,1004],'description':'Large white chin and chest bib.','evidence':'observed'},
 {'id':'paws','region':'visible paws','source':['photo-02','photo-03','photo-05','photo-06'],'description':'White paws with orange markings on foreleg; exact standing sock boundaries need inference.','evidence':'partly_observed'},
 {'id':'back_nape','region':'dorsal coat','source':['photo-01','photo-03'],'description':'Black/orange mottled back and nape, no complete dorsal white collar.','evidence':'observed'},
 {'id':'eyes','region':'eyes','source':['photo-05'],'description':'Yellow-green irises; narrow pupils and partially closed eyelids in this lighting.','evidence':'observed'},
 {'id':'tail','region':'tail','source':['photo-05','photo-06'],'description':'Dark mottled tail, black tip supported by photo-06; lifted standing curve will be inferred.','evidence':'partly_observed'},
 {'id':'standing_proportions','region':'body and legs','source':[],'description':'Neutral standing limb lengths and hidden surfaces are inferred, not true measurements.','evidence':'inferred'}]
out2=HERE/'02-identity';out2.mkdir(exist_ok=True)
(out2/'features.json').write_text(json.dumps({'method':'assistant visual annotation, manually checked POC; no detector implemented','features':features},ensure_ascii=False,indent=2))
annot=Image.fromarray(im.copy());dr=ImageDraw.Draw(annot)
for n,f in enumerate(features,1):
 if 'bbox_photo05' in f:
  b=f['bbox_photo05'];dr.rectangle(b,outline=(0,235,160),width=3);dr.text((b[0],b[1]-16),str(n)+' '+f['id'],fill=(0,150,90),stroke_width=1,stroke_fill='white')
annot.crop((480,540,960,1120)).resize((720,870)).save(out2/'face-evidence.png')
print(json.dumps({'P01':'complete_review_required','P02':'annotated','mask_pixels':int(mask.sum())}))
