"""Bake local photographic samples to the existing cat UVs; never alter mesh/rig.

The landmarks below are a manual, approximate registration for this one animal.
This is an appearance prototype, not calibrated photogrammetry or an automated
reconstruction. Pixel samples come from the user's photos, without a generative
image model. UV padding is technical texture baking, not invented image detail.
"""
from pathlib import Path
import bpy, json, hashlib
import numpy as np
from mathutils import Vector

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
bpy.ops.wm.open_mainfile(filepath=str(OUT/'original-preview.blend'))
cat=bpy.data.objects['SKM_Cat_Domestic_Shorthair']
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
mesh=cat.data
mesh.calc_loop_triangles()
SIZE=2048

def digest_geometry():
    obj={'vertices':[list(v.co) for v in mesh.vertices],
         'faces':[list(p.vertices) for p in mesh.polygons],
         'uv':[[list(d.uv) for d in u.data] for u in mesh.uv_layers],
         'weights':[[[g.group,g.weight] for g in v.groups] for v in mesh.vertices],
         'bones':[[b.name,list(b.head_local),list(b.tail_local)] for b in rig.data.bones]}
    return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()

original_hash=digest_geometry()
photos={}
def image_array(name):
    if name not in photos:
        im=bpy.data.images.load(str(ROOT/'example'/name),check_existing=True)
        # Sampling coordinates use the original JPEG, with top-left origin.
        im.colorspace_settings.name='Non-Color'
        w,h=im.size
        a=np.empty(w*h*4,dtype=np.float32);im.pixels.foreach_get(a)
        photos[name]=a.reshape(h,w,4)[::-1,:,:3].copy()
    return photos[name]

def sample(name,xy,reference=(1108,1477),gain=1.0):
    a=image_array(name);h,w=a.shape[:2]
    x=np.clip(xy[:,0]/reference[0]*(w-1),0,w-1.001)
    y=np.clip(xy[:,1]/reference[1]*(h-1),0,h-1.001)
    xi=x.astype(int);yi=y.astype(int);fx=(x-xi)[:,None];fy=(y-yi)[:,None]
    rgb=(a[yi,xi]*(1-fx)+a[yi,xi+1]*fx)*(1-fy)+(a[yi+1,xi]*(1-fx)+a[yi+1,xi+1]*fx)*fy
    return np.clip(rgb*gain,0,1)

def smooth(a,b,x):
    t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)

def strip(s,t,top,bottom,knots=None):
    s=np.clip(s,0,1);t=np.clip(t,0,1)
    top=np.array(top);bottom=np.array(bottom)
    if knots is None:knots=np.linspace(0,1,len(top))
    a=np.stack([np.interp(s,knots,top[:,i]) for i in range(2)],axis=1)
    b=np.stack([np.interp(s,knots,bottom[:,i]) for i in range(2)],axis=1)
    return a*t[:,None]+b*(1-t[:,None])

def ribbon(t,width,centers,halfwidth=22):
    centers=np.array(centers);knots=np.linspace(0,1,len(centers))
    t=np.clip(t,0,1)
    p=np.stack([np.interp(t,knots,centers[:,i]) for i in range(2)],axis=1)
    tangents=np.gradient(centers,axis=0)
    tangents/=np.maximum(np.linalg.norm(tangents,axis=1)[:,None],1e-8)
    normal=np.stack([-np.interp(t,knots,tangents[:,1]),np.interp(t,knots,tangents[:,0])],axis=1)
    return p+normal*np.clip(width,-1,1)[:,None]*halfwidth

# Photo landmark registration: local x = anatomical left; y = up; z = forward.
face_xy=np.array([[-.01858,.246],[.01858,.246],[0,.229],[0,.273],[0,.208],
                  [-.047,.24],[.047,.24],[-.032,.283],[.032,.283],
                  [-.045,.307],[.045,.307],[-.05,.215],[.05,.215]],dtype=float)
face_photo=np.array([[651,876],[816,876],[739,974],[737,757],[728,1013],
                     [553,889],[892,898],[597,706],[858,707],
                     [526,573],[934,565],[606,980],[868,980]],dtype=float)

def fit_tps(src,dst):
    src=src*10
    r2=((src[:,None,:]-src[None,:,:])**2).sum(2)
    kernel=r2*np.log(np.maximum(r2,1e-12))
    affine=np.c_[np.ones(len(src)),src]
    matrix=np.block([[kernel+np.eye(len(src))*1e-7,affine],[affine.T,np.zeros((3,3))]])
    coeff=np.linalg.solve(matrix,np.r_[dst,np.zeros((3,2))])
    def transform(points):
        points=points*10
        r2=((points[:,None,:]-src[None,:,:])**2).sum(2)
        return np.c_[r2*np.log(np.maximum(r2,1e-12)),np.ones(len(points)),points]@coeff
    return transform
face_transform=fit_tps(face_xy,face_photo)

def body_color(p,n):
    x,y,z=p.T
    s=np.clip((.14-z)/.30,0,1)
    lower=.117+.025*s
    t=np.clip((y-lower)/(.253-lower),0,1)
    right=sample('S__48340997.jpg',strip(s,t,
        [[478,397],[638,491],[833,637],[988,831]],
        [[330,676],[460,783],[621,938],[863,1120]]),gain=1.08)
    left=sample('S__48381959_0.jpg',strip(s,t,
        [[327,731],[466,766],[611,833],[724,965]],
        [[324,861],[442,918],[557,1000],[655,1093]]),reference=(869,1884),gain=1.03)
    alpha=smooth(-.004,.004,x)
    col=right*(1-alpha[:,None])+left*alpha[:,None]
    dorsal=sample('<redacted-id>.jpg',strip(s,
        np.clip(.5+x/.115,0,1),
        [[343,1050],[376,1253],[457,1475],[633,1728]],
        [[585,1018],[721,1207],[840,1390],[879,1561]]),reference=(1152,2048),gain=1.22)
    top=smooth(.42,.88,n[:,1])*smooth(.212,.241,y)
    col=col*(1-top[:,None])+dorsal*top[:,None]
    # White underside follows observed belly/chest, but hidden boundaries remain approximate.
    belly_xy=np.c_[530+(x/.058)*52, np.interp(s,[0,.5,1],[768,954,1127])]
    belly=sample('S__48381960_0.jpg',belly_xy,reference=(869,1884),gain=1.05)
    under=(1-smooth(.125,.17,y))*smooth(-.035,.02,-n[:,1])
    col=col*(1-under[:,None])+belly*under[:,None]
    return col

def shade(p,n,weights,orig):
    x,y,z=p.T
    col=body_color(p,n)
    evidence=np.full(len(p),.65,dtype=np.float32)
    # Photograph of front chest. A white bib is visible in every relevant view.
    chest=sample('S__48381957_0.jpg',np.c_[742+x*1900,1054-(y-.15)*480],gain=1.0)
    front=smooth(.12,.165,z)*(1-smooth(.221,.245,y))
    col=col*(1-front[:,None])+chest*front[:,None]
    # Head photo warp on facial surfaces; posterior skull remains a conservative dark fur sample.
    headw=weights[:,5]+weights[:,6]+weights[:,7]+weights[:,12]+weights[:,13]
    face=sample('S__48381957_0.jpg',face_transform(p[:,:2]),gain=1.00)
    skull=sample('S__48381957_0.jpg',np.c_[707+x*1000,686+(y-.25)*700],gain=1.0)
    facing=smooth(.188,.222,z)
    head=skull*(1-facing[:,None])+face*facing[:,None]
    hw=smooth(.10,.82,headw)*smooth(.185,.212,y)
    col=col*(1-hw[:,None])+head*hw[:,None]
    evidence=np.maximum(evidence,hw*.88)
    # Ears use the corresponding side of the same photo, preserving differing orange tips.
    earw=weights[:,14]+weights[:,15]
    ea=sample('S__48381957_0.jpg',face_transform(p[:,:2]),gain=1.0)
    ew=smooth(.1,.8,earw)
    col=col*(1-ew[:,None])+ea*ew[:,None]
    # Forelegs: use actual fur from the resting right foreleg. Inner-side correspondence is uncertain.
    fw=weights[:,18:25].sum(1)+weights[:,26:33].sum(1)
    t=np.clip((.18-y)/.175,0,1)
    frontxy=ribbon(t,(z-.115)/.026,[[373,611],[292,650],[225,658],[164,653],[126,638]],halfwidth=19)
    fcol=sample('S__48340997.jpg',frontxy,gain=1.08)
    fblend=smooth(.12,.75,fw)*(1-smooth(.155,.195,y))
    col=col*(1-fblend[:,None])+fcol*fblend[:,None]
    # Rear legs use an unfolded leg reference from the outdoor side view.
    rw=weights[:,34:48].sum(1)
    rt=np.clip((.16-y)/.155,0,1)
    rearxy=ribbon(rt,(z+.119)/.035,[[689,1028],[677,1093],[638,1140],[583,1181],[550,1206]],halfwidth=20)
    rcol=sample('S__48381959_0.jpg',rearxy,reference=(869,1884),gain=1.02)
    rb=smooth(.15,.8,rw)*(1-smooth(.17,.21,y))
    col=col*(1-rb[:,None])+rcol*rb[:,None]
    # Every visible paw has white socks; sample an actual white paw area.
    feet=sample('S__48381957_0.jpg',np.c_[770+(x/.06)*30,1125+(z/.25)*12],gain=1.0)
    footw=(1-smooth(.02,.045,y))*np.clip(fw+rw,0,1)
    col=col*(1-footw[:,None])+feet*footw[:,None]
    evidence=np.where(np.maximum(fblend,rb)>.5,.45,evidence)
    # Tail detail is only partly observed; use visible tail pixels, with inferred wraparound.
    tw=weights[:,48:52].sum(1)
    tt=np.clip((-z-.163)/.206,0,1)
    tailxy=ribbon(tt,x/.011,[[782,1004],[801,1082],[819,1142],[843,1170]],halfwidth=9)
    tcol=sample('S__48381959_0.jpg',tailxy,reference=(869,1884),gain=1.02)
    tb=smooth(.08,.8,tw)
    col=col*(1-tb[:,None])+tcol*tb[:,None]
    evidence=np.where(tb>.5,.35,evidence)
    # Preserve the existing pupil geometry and replace only the iris hue.
    eye=weights[:,10]+weights[:,11]
    eyecol=orig[:,:3].copy()
    yellow=(eyecol[:,1]>.35)&(eyecol[:,0]>.25)&(eyecol[:,2]<.4)
    eyecol[yellow]=[.49,.46,.22]
    eb=smooth(.15,.8,eye)
    col=col*(1-eb[:,None])+eyecol*eb[:,None]
    mouth=weights[:,8]+weights[:,9]
    col=col*(1-mouth[:,None])+orig[:,:3]*mouth[:,None]
    return np.clip(col,0,1),evidence

origim=bpy.data.images.get('Cat_Domestic_Shorthair_COL_2k.png')
origim.colorspace_settings.name='Non-Color'
orig=np.empty(SIZE*SIZE*4,dtype=np.float32);origim.pixels.foreach_get(orig);orig=orig.reshape(SIZE,SIZE,4)
texture=np.zeros((SIZE,SIZE,4),dtype=np.float32);texture[:,:,3]=1
coverage=np.zeros((SIZE,SIZE),dtype=bool)
confidence=np.zeros((SIZE,SIZE),dtype=np.float32)
positions=np.array([v.co[:] for v in mesh.vertices],dtype=np.float32)
normals=np.array([v.normal[:] for v in mesh.vertices],dtype=np.float32)
allweights=np.zeros((len(mesh.vertices),len(cat.vertex_groups)),dtype=np.float32)
for v in mesh.vertices:
    for g in v.groups:allweights[v.index,g.group]=g.weight
uv=mesh.uv_layers[0].data
for tri in mesh.loop_triangles:
    ids=list(tri.vertices)
    uvp=np.array([uv[i].uv[:] for i in tri.loops],dtype=float)*SIZE-.5
    xmin=max(0,int(np.floor(uvp[:,0].min())));xmax=min(SIZE-1,int(np.ceil(uvp[:,0].max())))
    ymin=max(0,int(np.floor(uvp[:,1].min())));ymax=min(SIZE-1,int(np.ceil(uvp[:,1].max())))
    xx,yy=np.meshgrid(np.arange(xmin,xmax+1),np.arange(ymin,ymax+1))
    pts=np.c_[xx.ravel(),yy.ravel()]
    mat=np.c_[uvp[1]-uvp[0],uvp[2]-uvp[0]]
    if abs(np.linalg.det(mat))<1e-10:continue
    bc=(pts-uvp[0])@np.linalg.inv(mat).T
    bary=np.c_[1-bc.sum(1),bc]
    inside=(bary>=-1e-7).all(1)
    if not inside.any():continue
    b=bary[inside];qx=pts[inside,0].astype(int);qy=pts[inside,1].astype(int)
    p=b@positions[ids];n=b@normals[ids];n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-8)
    w=b@allweights[ids]
    color,cf=shade(p,n,w,orig[qy,qx])
    texture[qy,qx,:3]=color;confidence[qy,qx]=cf;coverage[qy,qx]=True
    if tri.index%400==0:print('Triangle',tri.index,flush=True)

# Extend edge texels by 12 pixels into empty UV space, avoiding minification seams.
valid=coverage.copy()
for _ in range(12):
    accum=np.zeros_like(texture);counts=np.zeros((SIZE,SIZE),dtype=np.float32)
    for dy,dx in [(1,0),(-1,0),(0,1),(0,-1)]:
        rolled=np.roll(valid,(dy,dx),(0,1))
        if dy==1:rolled[0]=False
        if dy==-1:rolled[-1]=False
        if dx==1:rolled[:,0]=False
        if dx==-1:rolled[:,-1]=False
        accum+=np.roll(texture,(dy,dx),(0,1))*rolled[:,:,None]
        counts+=rolled
    new=(~valid)&(counts>0)
    texture[new]=accum[new]/counts[new,None];valid|=new

(OUT/'textures').mkdir(exist_ok=True)
im=bpy.data.images.new('Cat_Photo_BaseColor_2k',width=SIZE,height=SIZE,alpha=True)
im.colorspace_settings.name='sRGB';im.pixels.foreach_set(texture.ravel());im.update()
im.filepath_raw=str(OUT/'textures/Cat_Photo_BaseColor_2k.png');im.file_format='PNG';im.save()
mat=cat.data.materials[0]
node=next(n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE')
origim.colorspace_settings.name='sRGB'
node.image=im
im.pack()
assert digest_geometry()==original_hash, 'Geometry/UV/skin/rig unexpectedly changed'
for a in bpy.data.actions:a.use_fake_user=True
scene=bpy.context.scene
scene.render.resolution_x=1400;scene.render.resolution_y=1050
scene.cycles.samples=48
points=[cat.matrix_world@v.co for v in mesh.vertices]
lo=Vector(tuple(min(p[i] for p in points) for i in range(3)));hi=Vector(tuple(max(p[i] for p in points) for i in range(3)))
center=(lo+hi)*.5;center.y-=.035;span=max(hi-lo)
cam=scene.camera;cam.data.ortho_scale=.72
def camera_view(direction):
    cam.location=center+Vector(direction)*span
    cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
camera_view((-2,-3,1.35))
# Set a material preview camera view for convenient opening in Blender.
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.type='MATERIAL'
            area.spaces.active.overlay.show_overlays=False
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'photo-skin-test.blend'))
validation={'original_geometry_uv_rig_sha256':original_hash,'result_geometry_uv_rig_sha256':digest_geometry(),
            'vertices':len(mesh.vertices),'triangles':len(mesh.loop_triangles),'uv_layers':[u.name for u in mesh.uv_layers],
            'source_animation_actions':len(bpy.data.actions),'texture_size':[SIZE,SIZE],
            'method':'Manual region registration and photographic pixel sampling into existing UV; no generative image model.',
            'limits':['Pose registration is approximate, not calibrated multi-view reconstruction.','Some inner legs, paws and tail wraparound use reused photo samples.','Lighting is partially present in input pixels; this is not measured albedo.','Confidence labels are editorial region estimates, not calibrated probabilities.']}
(OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
for name,direction in [('front-right',(-2,-3,1.35)),('front-left',(2,-3,1.35)),('right',(-3,0,.8)),('back-top',(1.8,2.5,3.5))]:
    camera_view(direction)
    scene.render.filepath=str(OUT/'preview'/('photo-'+name+'.png'))
    bpy.ops.render.render(write_still=True)
camera_view((-2,-3,1.35));node.image=origim
scene.render.filepath=str(OUT/'preview/original-front-right.png');bpy.ops.render.render(write_still=True)
node.image=im
bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=cat
bpy.ops.export_scene.gltf(filepath=str(OUT/'photo-skin-test.glb'),export_format='GLB',use_selection=True,export_animations=False,export_yup=True)
node.image=origim
bpy.ops.export_scene.gltf(filepath=str(OUT/'original-comparison.glb'),export_format='GLB',use_selection=True,export_animations=False,export_yup=True)
print('BAKE COMPLETE',json.dumps(validation),flush=True)
