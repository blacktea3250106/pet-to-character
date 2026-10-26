"""Rasterize the unchanged mesh in the previously fitted source camera for manual review."""
from pathlib import Path
import json, numpy as np
from PIL import Image, ImageDraw

P=Path(__file__).resolve().parent
OUT=P/'10-style-recovery'/'registration';OUT.mkdir(exist_ok=True)

def frame(az,el):
    a,e=np.deg2rad([az,el]);d=np.array([np.cos(a)*np.cos(e),np.sin(a)*np.cos(e),np.sin(e)])
    r=np.array([-np.sin(a),np.cos(a),0]);u=np.cross(d,r);return r,u,d

def raster(vertices,tris,uv,params,size):
    H,W=size;s,tx,ty,az,el=params;r,u,d=frame(az,el)
    q=np.stack([s*(vertices@r)+tx,-s*(vertices@u)+ty],1);depth=vertices@d
    zbuf=np.full((H,W),-np.inf);tid=np.full((H,W),-1,np.int32)
    bary=np.zeros((H,W,3),np.float32)
    for i,t in enumerate(tris):
        a,b,c=q[t]
        x0,y0=np.maximum(np.floor(np.min(q[t],0)),[0,0]).astype(int)
        x1,y1=np.minimum(np.ceil(np.max(q[t],0)),[W-1,H-1]).astype(int)
        if x1<x0 or y1<y0:continue
        xs,ys=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
        den=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        if abs(den)<1e-10:continue
        l1=((xs-a[0])*(c[1]-a[1])-(ys-a[1])*(c[0]-a[0]))/den
        l2=((b[0]-a[0])*(ys-a[1])-(b[1]-a[1])*(xs-a[0]))/den
        weights=np.stack([1-l1-l2,l1,l2],-1)
        z=weights@depth[t]
        sub=zbuf[y0:y1+1,x0:x1+1]
        hit=(weights.min(-1)>=-1e-5)&(z>sub)
        sub[hit]=z[hit];tid[y0:y1+1,x0:x1+1][hit]=i
        bary[y0:y1+1,x0:x1+1][hit]=weights[hit]
    valid=tid>=0
    uvmap=np.zeros((H,W,2),np.float32);pos=np.zeros((H,W,3),np.float32)
    uvmap[valid]=(uv[tid[valid]]*bary[valid,:,None]).sum(1)
    pos[valid]=(vertices[tris[tid[valid]]]*bary[valid,:,None]).sum(1)
    return tid,bary,pos,uvmap,zbuf

if __name__=='__main__':
    m=np.load(P/'06c-raw-single/mesh.npz');v,t,uv=m['verts'],m['tris'],m['tri_uv']
    params=json.loads((P/'08b-coat/processing-report.json').read_text())['camera']
    H,W=1024,1536
    tid,bary,pos,uvmap,zbuf=raster(v,t,uv,params,(H,W));valid=tid>=0
    tex=np.asarray(Image.open(next((P/'06c-raw-single').glob('material-*.png'))).convert('RGB'))
    tx=np.clip(np.rint(uvmap[...,0]*tex.shape[1]-.5).astype(int),0,tex.shape[1]-1)
    ty=np.clip(np.rint((1-uvmap[...,1])*tex.shape[0]-.5).astype(int),0,tex.shape[0]-1)
    image=np.full((H,W,3),190,np.uint8);image[valid]=tex[ty[valid],tx[valid]]
    Image.fromarray(image).save(OUT/'native-aligned.png')
    for name,file in [('native-grid',OUT/'native-aligned.png'),('reference-grid',P/'04b-single-reference/standing.png')]:
        img=Image.open(file).convert('RGB');draw=ImageDraw.Draw(img)
        for x in range(0,W,100):draw.line([(x,0),(x,H)],fill=(120,180,180),width=1);draw.text((x+2,5),str(x),fill='red',stroke_width=1,stroke_fill='white')
        for y in range(100,H,100):draw.line([(0,y),(W,y)],fill=(120,180,180),width=1);draw.text((5,y+2),str(y),fill='red',stroke_width=1,stroke_fill='white')
        img.save(OUT/(name+'.png'))
    np.savez_compressed(OUT/'gbuffer.npz',tri_id=tid,bary=bary,pos=pos,uv=uvmap,depth=zbuf)
    (OUT/'camera.json').write_text(json.dumps({'params':params,'size':[H,W],'mesh':'06c-raw-single/mesh.npz','meaning':'Same camera as the failed global projection; manual local alignment not yet performed.'},indent=2))
    print('ALIGNMENT_REVIEW_READY')
