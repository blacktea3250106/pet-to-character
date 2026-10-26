"""Semantic coat regions -> 3D material -> original UV atlas.

The region definitions are manually interpreted from photos, not an automatic
pet recognition model. This technical UV bake has no photographic pixel source.
Run with Blender --background --factory-startup --python build.py.
"""
from pathlib import Path
import bpy, json, hashlib, sys
import numpy as np
from mathutils import Vector

OUT=Path(__file__).resolve().parent
SOURCE=OUT.parent/'texture-transfer-v001'
FEATURES=json.loads((OUT/'coat-features.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(SOURCE/'original-preview.blend'))
cat=bpy.data.objects['SKM_Cat_Domestic_Shorthair'];mesh=cat.data
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
mesh.calc_loop_triangles();SIZE=2048

def digest():
    data={'vertices':[list(v.co) for v in mesh.vertices],
          'faces':[list(p.vertices) for p in mesh.polygons],
          'uv':[[list(d.uv) for d in u.data] for u in mesh.uv_layers],
          'weights':[[[g.group,g.weight] for g in v.groups] for v in mesh.vertices],
          'bones':[[b.name,list(b.head_local),list(b.tail_local)] for b in rig.data.bones]}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
original_hash=digest()
palette={k:np.array([int(v[i:i+2],16)/255 for i in (1,3,5)]) for k,v in FEATURES['palette_srgb'].items()}

def polygon(points,poly):
    x,y=points.T;inside=np.zeros(len(points),dtype=bool)
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if a[1]==b[1]:continue
        inside^=((a[1]>y)!=(b[1]>y))&(x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
    return inside

def shade(p,n,w,orig,tri):
    x,y,z=p.T
    rgb=np.tile(palette['black'],(len(p),1))
    s=(.14-z)/.30;t=(y-(.117+.025*np.clip(s,0,1)))/(.253-(.117+.025*np.clip(s,0,1)))
    st=np.c_[s,t]
    # Semantic patches are polygons in anatomy space. Angular boundaries remain
    # separate from geometric facets; neither input lighting nor fur is sampled.
    orange=np.zeros(len(p),bool)
    for side,key in [(x<0,'orange_polygons_right'),(x>=0,'orange_polygons_left')]:
        for poly in FEATURES[key]:orange|=side&polygon(st,poly)
    rgb[orange]=palette['orange']
    # Modest, continuous dorsal islands bridge the side maps.
    dorsal=(n[:,1]>.70)&(y>.236)&(z<.11)&(z>-.175)
    stripes=((s>.265)&(s<.34))|((s>.51)&(s<.59))|((s>.77)&(s<.86))
    rgb[dorsal]=palette['black'];rgb[dorsal&stripes]=palette['orange']
    belly=(y<.142+.01*np.clip(s,0,1))&(abs(x)<.047)&(n[:,1]<.1)
    rgb[belly]=palette['white']
    # Collar/bib, not all of the shoulder.
    bib=(z>.140)&(y<.229)&(abs(x)<.044)&(z>.154-2*(.2-y)**2)
    rgb[bib]=palette['white']
    collar=(z>.16)&(z<.192)&(y>.201)&(y<.239)&(abs(x)>.031)
    rgb[collar]=palette['white']
    # Legs retain different orange and black upper patches, white socks.
    front=w[:,18:25].sum(1)+w[:,26:33].sum(1)
    rear=w[:,34:48].sum(1)
    fl=(front>.45)&(y<.17);rl=(rear>.45)&(y<.16)
    rgb[fl|rl]=palette['black']
    rgb[fl&(y<.094)&(y>.027)]=palette['orange']
    rgb[rl&(y<.090)&(y>.035)]=palette['orange']
    socks=(front+rear>.38)&(y<.047+(.008*(x>0)))
    rgb[socks]=palette['white']
    wrist=fl&(y>.027)&(y<.040)&(abs(x)>.036)&(z>.116)
    rgb[wrist]=palette['orange']
    # Head features registered to the asset's eyes/nose, not to a rectangular photo.
    headw=w[:,5]+w[:,6]+w[:,7]+w[:,12]+w[:,13]
    head=(headw>.48)&(y>.202)
    rgb[head]=palette['black']
    face=head&(z>.205)
    chin=face&(y<.226)&((abs(x)>.010)|(y<.216))
    rgb[chin]=palette['white']
    # Subject's right orange cheek surrounds the eye, left stays dark.
    right=face&(x<-.010)&polygon(np.c_[x,y],[[-.052,.235],[-.047,.253],[-.031,.258],[-.023,.251],[-.011,.241],[-.014,.228],[-.031,.225],[-.043,.230]])
    rgb[right]=palette['orange']
    brow_r=face&polygon(np.c_[x,y],[[-.029,.249],[-.031,.260],[-.020,.266],[-.010,.262],[-.014,.253]])
    brow_l=face&polygon(np.c_[x,y],[[.008,.252],[.010,.270],[.019,.272],[.025,.261],[.039,.258],[.035,.249],[.022,.253]])
    rgb[brow_r|brow_l]=palette['orange']
    # Small orange crown fork, with a broad uninterrupted dark nasal bridge.
    crown=head&(y>.267)&(z>.211)&(x>.000)&(x<.018)&(y<.279-abs(x-.008)*.5)
    rgb[crown]=palette['orange']
    muzzle=face&(y<.228)&(y>.216)&(abs(x)<.023)&(abs(x)>.010)&(z>.241)
    rgb[muzzle]=palette['orange']*.75+palette['white']*.25
    nose=(z>.254)&(abs(x)<.010)&(y<.235)&(y>.221)
    rgb[nose]=palette['nose']
    # Ear cartilage is subdued; tips are orange as observed.
    ear=w[:,14]+w[:,15];e=ear>.35
    rgb[e]=palette['black']
    rgb[e&(n[:,2]>.2)]=palette['inner_ear']
    rgb[e&(y>.299-abs(x)*.065)]=palette['orange']
    tw=w[:,48:52].sum(1);tail=tw>.5;tt=(-z-.163)/.206
    rgb[tail]=palette['black']
    rings=((tt>.08)&(tt<.22))|((tt>.42)&(tt<.54))|((tt>.69)&(tt<.77))
    rgb[tail&rings]=palette['orange']*.8
    # Preserve sculpted eye/pupil and mouth topology and original UV components.
    eye=w[:,10]+w[:,11];em=eye>.55
    eyecol=orig[:,:3].copy()
    iris=(eyecol[:,1]>.30)&(eyecol[:,0]>.20)&(eyecol[:,2]<.45)
    eyecol[iris]=palette['iris'];rgb[em]=eyecol[em]
    tongue=w[:,8]+w[:,9];rgb[tongue>.5]=orig[tongue>.5,:3]
    # Very subtle constant-per-face pigment variation, no direction-dependent light.
    variation=1+(((tri*73)%19)/18-.5)*.08
    rgb[~em]*=variation
    return np.clip(rgb,0,1)

original=bpy.data.images.get('Cat_Domestic_Shorthair_COL_2k.png')
original.colorspace_settings.name='Non-Color'
orig=np.empty(SIZE*SIZE*4,np.float32);original.pixels.foreach_get(orig);orig=orig.reshape(SIZE,SIZE,4)
texture=np.zeros((SIZE,SIZE,4),np.float32);texture[:,:,3]=1
coverage=np.zeros((SIZE,SIZE),bool)
positions=np.array([v.co[:] for v in mesh.vertices],np.float32)
normals=np.array([v.normal[:] for v in mesh.vertices],np.float32)
weights=np.zeros((len(mesh.vertices),len(cat.vertex_groups)),np.float32)
for v in mesh.vertices:
    for g in v.groups:weights[v.index,g.group]=g.weight
uv=mesh.uv_layers[0].data
for tri in mesh.loop_triangles:
    ids=list(tri.vertices);uvp=np.array([uv[i].uv[:] for i in tri.loops])*SIZE-.5
    xmin=max(0,int(np.floor(uvp[:,0].min())));xmax=min(SIZE-1,int(np.ceil(uvp[:,0].max())))
    ymin=max(0,int(np.floor(uvp[:,1].min())));ymax=min(SIZE-1,int(np.ceil(uvp[:,1].max())))
    xx,yy=np.meshgrid(np.arange(xmin,xmax+1),np.arange(ymin,ymax+1));pts=np.c_[xx.ravel(),yy.ravel()]
    matrix=np.c_[uvp[1]-uvp[0],uvp[2]-uvp[0]]
    if abs(np.linalg.det(matrix))<1e-10:continue
    bc=(pts-uvp[0])@np.linalg.inv(matrix).T;bary=np.c_[1-bc.sum(1),bc];inside=(bary>=-1e-7).all(1)
    if not inside.any():continue
    b=bary[inside];qx=pts[inside,0].astype(int);qy=pts[inside,1].astype(int)
    p=b@positions[ids];n=b@normals[ids];n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-8)
    texture[qy,qx,:3]=shade(p,n,b@weights[ids],orig[qy,qx],tri.index);coverage[qy,qx]=True

valid=coverage.copy()
for _ in range(12):
    accum=np.zeros_like(texture);counts=np.zeros((SIZE,SIZE),np.float32)
    for dy,dx in [(1,0),(-1,0),(0,1),(0,-1)]:
        rolled=np.roll(valid,(dy,dx),(0,1))
        if dy==1:rolled[0]=False
        if dy==-1:rolled[-1]=False
        if dx==1:rolled[:,0]=False
        if dx==-1:rolled[:,-1]=False
        accum+=np.roll(texture,(dy,dx),(0,1))*rolled[:,:,None];counts+=rolled
    new=(~valid)&(counts>0);texture[new]=accum[new]/counts[new,None];valid|=new

# Use a lossless data PNG writer so our explicit sRGB palette bytes stay exact.
# This serializes the technical UV bake; no input photographs are edited.
import struct,zlib
pixels=(np.clip(texture[::-1,:,:3],0,1)*255+.5).astype(np.uint8)
def chunk(tag,data):return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
raw=b''.join(b'\0'+row.tobytes() for row in pixels)
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',SIZE,SIZE,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b'')
texture_path=OUT/'textures/Cat_Semantic_BaseColor_2k.png';texture_path.write_bytes(png)
im=bpy.data.images.load(str(texture_path));im.colorspace_settings.name='sRGB';im.pack()
original.colorspace_settings.name='sRGB'
node=next(n for n in cat.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE');node.image=im
for a in bpy.data.actions:a.use_fake_user=True
scene=bpy.context.scene;scene.cycles.samples=32
scene.render.resolution_x=1400;scene.render.resolution_y=1050
scene.view_settings.view_transform='AgX'
cam=scene.camera;cam.data.ortho_scale=.72
points=[cat.matrix_world@v.co for v in mesh.vertices]
lo=Vector(tuple(min(p[i] for p in points) for i in range(3)));hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
center=(lo+hi)*.5;center.y-=.035;span=max(hi-lo)
def view(direction):
    cam.location=center+Vector(direction)*span
    cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
view((-2,-3,1.35))
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.type='MATERIAL';area.spaces.active.overlay.show_overlays=False
assert digest()==original_hash
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'semantic-skin-test.blend'))
validation={'method':'Manually interpreted semantic coat regions, polygon simplification, original-UV raster bake. No photo RGB projection.',
            'vertices':len(mesh.vertices),'triangles':len(mesh.loop_triangles),'animation_actions_retained':len(bpy.data.actions),
            'original_geometry_uv_rig_sha256':original_hash,'result_geometry_uv_rig_sha256':digest(),
            'texture_size':[SIZE,SIZE],'padding_pixels':12,
            'limits':['Manual feature interpretation, not an automated pipeline.','Unobserved boundaries are inferred.','Original narrow face and body proportions differ from cat.png.','This stage is a simplified semantic layout, not final texture art.']}
(OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
for name,direction in [('front-right',(-2,-3,1.35)),('front-left',(2,-3,1.35)),('right',(-3,0,.8)),('back-top',(1.8,2.5,3.5))]:
    view(direction);scene.render.filepath=str(OUT/'preview'/('semantic-'+name+'.png'));bpy.ops.render.render(write_still=True)
view((-2,-3,1.35))
bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=cat
bpy.ops.export_scene.gltf(filepath=str(OUT/'semantic-skin-test.glb'),export_format='GLB',use_selection=True,export_animations=False,export_yup=True)
print('SEMANTIC BAKE COMPLETE',json.dumps(validation),flush=True)
