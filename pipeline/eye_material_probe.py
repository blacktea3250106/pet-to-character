"""Manual eye-opening masks transferred through the validated single-case correspondence."""
import json
from pathlib import Path
import numpy as np,cv2
from scipy import ndimage
from PIL import Image
P=Path(__file__).resolve().parent;ROOT=P/'10-style-recovery';OUT=ROOT/'eye-material';OUT.mkdir(exist_ok=True)
polygons={
 'cat_right_viewer_left':[[1077,254],[1102,262],[1138,281],[1132,286],[1114,289],[1093,281],[1082,267]],
 'cat_left_viewer_right':[[1223,280],[1238,269],[1277,258],[1286,256],[1280,277],[1263,291],[1241,292]]
}
mask=np.zeros((1024,1536),np.uint8)
for poly in polygons.values():cv2.fillPoly(mask,[np.array(poly,np.int32)],255)
mask=cv2.erode(mask,np.ones((3,3),np.uint8),iterations=1)
Image.fromarray(mask).save(OUT/'source-eye-openings.png')
c=np.load(ROOT/'local-projection/surface-correspondence.npz');cov=c['coverage'];q=c['source_xy'];weight=c['weight'][cov]
eye=ndimage.map_coordinates(mask.astype(float)/255,[q[:,1]-.5,q[:,0]-.5],order=1,mode='constant',cval=0)
eye*=weight>.95
atlas=np.zeros(cov.shape,np.float32);atlas[cov]=eye
rough=.9-.6*atlas
dist,nearest=ndimage.distance_transform_edt(~cov,return_indices=True);pad=(~cov)&(dist<=16)
rough[pad]=rough[nearest[0][pad],nearest[1][pad]]
Image.fromarray(np.uint8(np.clip(rough,0,1)*255)).save(OUT/'roughness.png')
Image.fromarray(np.uint8(atlas*255)).save(OUT/'eye-mask.png')
report={'source_eye_polygons':polygons,'selection':'Manual visible eye openings; no iris-color heuristic or generic eye detector',
 'body_roughness':.9,'eye_roughness':.3,'metallic':0,'specular_ior_level':.15,
 'mask_texels':int((atlas>.5).sum()),'fraction_of_surface_texels':float((eye>.5).mean()),
 'geometry':'Original recessed eye geometry; no added eyeball or eyelid rig',
 'limitations':['Manual source polygon and alignment uncertainty','Source iris includes baked shading; physically accurate albedo not recovered','Eye motion/blinking not implemented'],
 'visual_pass':False,'status':'Candidate material probe awaiting real 3D render review'}
(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
