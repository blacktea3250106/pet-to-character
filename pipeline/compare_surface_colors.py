"""Compare base-color samples on geometrically corresponding surfaces, not UV pixels."""
import argparse,hashlib,io,json,struct
from pathlib import Path
import numpy as np
from PIL import Image


def base_image(path):
    blob=path.read_bytes();chunks={};offset=12
    while offset<len(blob):
        length,kind=struct.unpack_from('<II',blob,offset);chunks[kind]=blob[offset+8:offset+8+length];offset+=8+length
    d=json.loads(chunks[0x4e4f534a]);binary=chunks[0x004e4942]
    if len(d['materials'])!=1:raise ValueError('Multi-material color correspondence requires material-specific sampling')
    pbr=d['materials'][0]['pbrMetallicRoughness'];texture_info=pbr['baseColorTexture']
    if texture_info.get('texCoord',0)!=0 or texture_info.get('extensions'):raise ValueError('Non-default texture transform not supported')
    texture=d['textures'][texture_info['index']]
    sampler=d.get('samplers',[])[texture['sampler']] if 'sampler' in texture else {}
    if any(sampler.get(axis,10497)!=10497 for axis in ('wrapS','wrapT')):raise ValueError('Only repeat wrapping supported by this sampler')
    meta=d['images'][texture['source']];bv=d['bufferViews'][meta['bufferView']]
    data=binary[bv.get('byteOffset',0):bv.get('byteOffset',0)+bv['byteLength']]
    pixels=np.asarray(Image.open(io.BytesIO(data)).convert('RGB'),dtype=np.float64)/255
    linear=np.where(pixels<=.04045,pixels/12.92,((pixels+.055)/1.055)**2.4)
    return linear*np.array(pbr.get('baseColorFactor',[1,1,1,1]))[:3]


def sample(image,uv):
    h,w=image.shape[:2];x=uv[:,0]*w-.5;y=(1-uv[:,1])*h-.5
    ix=np.floor(x).astype(int);iy=np.floor(y).astype(int);tx=(x-ix)[:,None];ty=(y-iy)[:,None]
    values=(image[iy%h,ix%w]*(1-tx)+image[iy%h,(ix+1)%w]*tx)*(1-ty)+(image[(iy+1)%h,ix%w]*(1-tx)+image[(iy+1)%h,(ix+1)%w]*tx)*ty
    return np.where(values<=.0031308,12.92*values,1.055*np.maximum(values,0)**(1/2.4)-.055)*255


parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('candidate',type=Path);parser.add_argument('samples',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args();points=np.load(args.samples)
for role,path in [('source',args.source),('candidate',args.candidate)]:
    if hashlib.sha256(path.read_bytes()).hexdigest()!=str(points[role+'_sha256']):raise ValueError('Surface samples do not belong to these assets')
a=sample(base_image(args.source),points['source_uv']);b=sample(base_image(args.candidate),points['candidate_uv'])
per_sample=np.abs(a-b).mean(1)
report={'sample_count':len(a),'source_sha256':str(points['source_sha256']),'candidate_sha256':str(points['candidate_sha256']),
        'mean_absolute_rgb_error_255':float(per_sample.mean()),'median_absolute_rgb_error_255':float(np.median(per_sample)),
        'p95_absolute_rgb_error_255':float(np.percentile(per_sample,95)),'p99_absolute_rgb_error_255':float(np.percentile(per_sample,99)),
        'fraction_error_above_20':float(np.mean(per_sample>20)),
        'method':'Three interior samples per reduced triangle; nearest source surface and barycentric UV interpolation. Decode sRGB, bilinear-sample linear RGB with repeat wrapping, then report sRGB channel error.',
        'scope':'Unweighted surface color-change diagnostic from generated source; not photo reconstruction accuracy, identity acceptance or exact renderer pixel matching. Nearest-surface correspondence may be ambiguous near seams and close surfaces.',
        'restoration_review_trigger':bool(per_sample.mean()>5 or np.percentile(per_sample,95)>20),
        'trigger_status':'Initial diagnostic thresholds, not calibrated product acceptance','identity_or_art_pass':False}
args.output.write_text(json.dumps(report,indent=2));args.output.with_suffix('.executed.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps(report))
