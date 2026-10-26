"""Strict per-triangle color diagnostic, using manually authored coat regions.

No generated texture, photo projection, LAB clustering, automatic segmentation,
or automatic landmarks are used. Quad faces are explicitly represented by the
same triangles Blender already renders. No vertices are moved or added.
"""
from pathlib import Path
import sys,json,hashlib,collections
import bpy
import numpy as np
from mathutils import Vector

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from coat_regions import shade,palette,FEATURES
SOURCE=OUT.parent/'texture-transfer-v001'
bpy.ops.wm.open_mainfile(filepath=str(SOURCE/'original-preview.blend'))
cat=bpy.data.objects['SKM_Cat_Domestic_Shorthair'];old=cat.data
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE')
old.calc_loop_triangles()
verts=np.array([v.co[:] for v in old.vertices],dtype=np.float64)
normals=np.array([v.normal[:] for v in old.vertices],dtype=np.float64)
tris=np.array([t.vertices[:] for t in old.loop_triangles],dtype=np.int32)
source_polygons=[t.polygon_index for t in old.loop_triangles]
tri_uv={layer.name:[[list(layer.data[i].uv) for i in tri.loops] for tri in old.loop_triangles] for layer in old.uv_layers}
weights=np.zeros((len(verts),len(cat.vertex_groups)),dtype=np.float64)
for v in old.vertices:
    for g in v.groups:weights[v.index,g.group]=g.weight

def h(data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def surface_state(obj):
    me=obj.data;me.calc_loop_triangles()
    return {'vertices':[list(v.co) for v in me.vertices],
            'triangles':[list(t.vertices) for t in me.loop_triangles],
            'triangle_uv':{u.name:[[list(u.data[i].uv) for i in t.loops] for t in me.loop_triangles] for u in me.uv_layers},
            'weights':[[[g.group,g.weight] for g in v.groups] for v in me.vertices],
            'vertex_groups':[g.name for g in obj.vertex_groups],
            'object_matrix':[list(row) for row in obj.matrix_world],
            'bones':[[b.name,b.parent.name if b.parent else None,[list(row) for row in b.matrix_local],b.length] for b in rig.data.bones]}
def animations():
    result=[]
    for action in bpy.data.actions:
        curves=[]
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for f in bag.fcurves:
                        curves.append([f.data_path,f.array_index,[[list(k.co),list(k.handle_left),list(k.handle_right),k.interpolation] for k in f.keyframe_points]])
        result.append([action.name,curves])
    return result
before=surface_state(cat);before_hash=h(before);anim_before=h(animations())
source_polygon_count=len(old.polygons)

# Barycentric interior lattice gives area-like votes from manually authored regions.
# Source references are used by the human author of those regions, never as pixels here.
B=[]
for a in range(9):
    for b in range(9-a):
        c=8-a-b
        B.append([(a+1/3)/9,(b+1/3)/9,(c+1/3)/9])
B=np.array(B)
names=list(palette);colors=np.array([palette[n] for n in names])
labels=[];fractions=[];evidence=[]
for face_id,ids in enumerate(tris):
    p=B@verts[ids];n=B@normals[ids];n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-12)
    w=B@weights[ids]
    rgb=shade(p,n,w,np.zeros((len(B),4)),face_id)
    classification=((rgb[:,None,:]-colors[None,:,:])**2).sum(2).argmin(1)
    votes=np.bincount(classification,minlength=len(names));label=int(votes.argmax())
    labels.append(label);fractions.append(float(votes[label]/len(B)))
    c=verts[ids].mean(0);wm=weights[ids].mean(0)
    inferred=wm[48:52].sum()>.2 or (c[0]>0 and c[2]<.12) or (c[1]<.14 and abs(c[0])<.027)
    evidence.append('manual_inferred' if inferred else 'manual_reference_based')

# Optional explicit face-ID corrections are applied after region voting.
overrides_path=OUT/'face-overrides.json'
overrides=json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
for face_id,label in overrides.items():labels[int(face_id)]=names.index(label)

# Build the already-rendered triangles explicitly; preserve all original data.
me=bpy.data.meshes.new('Cat_original_render_triangles')
me.from_pydata(verts.tolist(),[],tris.tolist());me.update()
cat.data=me
for name in before['vertex_groups']:cat.vertex_groups.new(name=name)
for name,uvs in tri_uv.items():
    layer=me.uv_layers.new(name=name)
    for poly,uvset in zip(me.polygons,uvs):
        for loop,uv in zip(poly.loop_indices,uvset):layer.data[loop].uv=uv
for vi,row in enumerate(weights):
    for gi in np.nonzero(row)[0]:cat.vertex_groups[int(gi)].add([vi],float(row[gi]),'REPLACE')
assert h(surface_state(cat))==before_hash,'Rendered surface, UV, weights or bones changed'

attr=me.color_attributes.new(name='CoatFaceColor',type='FLOAT_COLOR',domain='CORNER')
me.color_attributes.active_color=attr
label_attr=me.attributes.new('coat_label','INT','FACE')
source_attr=me.attributes.new('source_polygon','INT','FACE')
corner_rgba=np.zeros((len(me.loops),4),np.float32);corner_rgba[:,3]=1
def srgb_to_linear(c):return np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4)
for p,label in zip(me.polygons,labels):
    # Fixed 4% peak-to-peak pigment variance, independent of illumination.
    variation=1+(((p.index*73+17)%101)/100-.5)*.04
    col=srgb_to_linear(np.clip(colors[label]*variation,0,1))
    corner_rgba[list(p.loop_indices),:3]=col
    p.use_smooth=False
    label_attr.data[p.index].value=label
    source_attr.data[p.index].value=source_polygons[p.index]
attr.data.foreach_set('color',corner_rgba.ravel())
mat=bpy.data.materials.new('CoatFaceColor_only');mat.use_nodes=True
nt=mat.node_tree;nt.nodes.clear()
out=nt.nodes.new('ShaderNodeOutputMaterial');bs=nt.nodes.new('ShaderNodeBsdfPrincipled')
vc=nt.nodes.new('ShaderNodeVertexColor');vc.layer_name='CoatFaceColor'
nt.links.new(vc.outputs['Color'],bs.inputs['Base Color']);nt.links.new(bs.outputs['BSDF'],out.inputs['Surface'])
bs.inputs['Roughness'].default_value=.92
me.materials.clear();me.materials.append(mat)
for a in bpy.data.actions:a.use_fake_user=True
assert h(animations())==anim_before,'Animation keyframes changed'
assert not any(n.type=='TEX_IMAGE' for n in nt.nodes)
actual=np.array([d.color[:] for d in attr.data])
assert all(np.array_equal(actual[p.loop_indices[0]],actual[i]) for p in me.polygons for i in p.loop_indices)

mapping={'schema':1,'mesh_triangle_signature':h({'vertices':verts.tolist(),'triangles':tris.tolist()}),
         'source_asset':'../texture-transfer-v001/source/SKM_Cat_Domestic_Shorthair.fbx',
         'color_names':names,'palette_srgb':FEATURES['palette_srgb'],'face_labels':labels,
         'pigment_variation':'1 + (((faceId * 73 + 17) % 101) / 100 - 0.5) * 0.04',
         'manual_evidence':evidence,
         'note':'Evidence labels are author judgments, not calibrated confidence. Face IDs require this exact source triangulation.'}
(OUT/'face-labels.json').write_text(json.dumps(mapping,ensure_ascii=False,separators=(',',':')))
scene=bpy.context.scene
for obj in bpy.data.objects:
    if obj.type=='LIGHT':obj.data.energy*=.28
scene.world.node_tree.nodes['Background'].inputs[1].default_value=.20
scene.render.resolution_x=1400;scene.render.resolution_y=1050;scene.cycles.samples=32
cam=scene.camera
world=np.array([(cat.matrix_world@v.co)[:] for v in me.vertices])
center=Vector(((world.min(0)+world.max(0))*.5).tolist());center.y-=.035
def view(direction,head=False):
    target=cat.matrix_world@Vector((0,.253,.216)) if head else center
    cam.location=target+Vector(direction)
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='ORTHO';cam.data.ortho_scale=.155 if head else .82
view((-1.2,-1.8,.80))
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.type='MATERIAL';area.spaces.active.overlay.show_overlays=False
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'face-color-test.blend'))
stats={'workflow':'Manual semantic regions -> 45 samples/triangle -> label vote -> CORNER colors -> flat shading. No image texture or new AI generation.',
       'vertices':len(me.vertices),'original_polygons':source_polygon_count,'triangles':len(me.polygons),
       'triangulation':'Original quads expanded into their existing render triangles; no added/moved vertices.',
       'rendered_surface_uv_weights_bones_sha256_before':before_hash,
       'rendered_surface_uv_weights_bones_sha256_after':h(surface_state(cat)),
       'animation_keyframes_sha256_before':anim_before,'animation_keyframes_sha256_after':h(animations()),
       'animations_retained':len(bpy.data.actions),'all_faces_constant_color':True,'material_image_texture_nodes':0,
       'labels':dict(collections.Counter(names[l] for l in labels)),
       'triangles_crossing_authored_color_boundaries':sum(f<1 for f in fractions),
       'sample_vote_agreement_is_not_identity_accuracy':True,
       'limits':['Manual authored masks are approximate; this is not an accuracy upper bound.',
                 'Strict face colors constrain boundary detail, especially eyes and face.',
                 'No automatic photo segmentation, LAB clustering or landmark detection has been implemented.',
                 'Rest-pose visual experiment only; GLB has no animation clips; Blender retains original actions.',
                 'No new evidence for hidden coat regions.']}
(OUT/'validation.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
for name,direction,head in [('front-right',(-1.2,-1.8,.80),False),('front',(0,-2,.22),False),('right',(-2,0,.25),False),('back-top',(.7,1,1.5),False),('face',(0,-1,.06),True)]:
    view(direction,head);scene.render.filepath=str(OUT/'preview'/('face-color-'+name+'.png'));bpy.ops.render.render(write_still=True)
view((-1.2,-1.8,.80))
bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=cat
bpy.ops.export_scene.gltf(filepath=str(OUT/'face-color-test.glb'),export_format='GLB',use_selection=True,
    export_animations=False,export_yup=True,export_vertex_color='ACTIVE',export_all_influences=True)
print('FACE COLOR VALIDATED',json.dumps(stats),flush=True)
