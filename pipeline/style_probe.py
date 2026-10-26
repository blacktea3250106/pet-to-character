"""Controlled render-only comparison; run in background Blender. No source edits."""
import ast, hashlib, json, math, sys
from pathlib import Path
import bpy, bmesh, numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE / '10-style-recovery'
ROOT.mkdir(exist_ok=True)
# Reuse inspected scene/render/stat helpers, without executing the old stage runner.
tree = ast.parse((HERE / 'blender_stage.py').read_text())
helpers = {'bsdf', 'make_mat', 'setup', 'render', 'export_npz', 'mesh_stats'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in helpers], type_ignores=[]), 'review_helpers', 'exec'))

variant = sys.argv[sys.argv.index('--') + 1]
assert variant in ['native', 'flat', 'uniform20k', 'clean-flat', 'local-color', 'eye-material']
texture_probe = variant in ['local-color','eye-material']
source = (ROOT/('local-color' if variant=='eye-material' else 'clean-flat') if texture_probe else HERE / ('07b-geometry' if variant == 'uniform20k' else '06c-raw-single')) / 'scene.blend'
OUT = ROOT / variant
OUT.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source))
cat = bpy.data.objects['Cat']
# Keep identical native texture and identical material for this geometry-only test.
for mat in cat.data.materials:
    p = bsdf(mat)
    p.inputs['Metallic'].default_value = 0
    p.inputs['Roughness'].default_value = .9
    p.inputs['Specular IOR Level'].default_value = .15
if variant == 'local-color':
    material=cat.data.materials[0];nt=material.node_tree
    tex=nt.nodes.new('ShaderNodeTexImage')
    tex.image=bpy.data.images.load(str(ROOT/'local-projection/local-color.png'),check_existing=False)
    nt.links.new(tex.outputs['Color'],bsdf(material).inputs['Base Color'])
if variant == 'eye-material':
    material=cat.data.materials[0];nt=material.node_tree
    tex=nt.nodes.new('ShaderNodeTexImage')
    tex.image=bpy.data.images.load(str(ROOT/'eye-material/roughness.png'),check_existing=False)
    tex.image.colorspace_settings.name='Non-Color'
    nt.links.new(tex.outputs['Color'],bsdf(material).inputs['Roughness'])
removed = []
if variant == 'clean-flat':
    bm = bmesh.new(); bm.from_mesh(cat.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=6.5e-7)
    remaining = set(bm.verts); groups=[]
    while remaining:
        first=remaining.pop(); group={first}; stack=[first]
        while stack:
            vertex=stack.pop()
            for edge in vertex.link_edges:
                other=edge.other_vert(vertex)
                if other in remaining:
                    remaining.remove(other); group.add(other); stack.append(other)
        groups.append(group)
    groups.sort(key=len, reverse=True)
    assert [len(g) for g in groups] == [2538,8,8,8,7,7], 'Unexpected source topology; manual review required'
    # Visually reviewed in the source front/clay: two eyebrow spikes and three whisker wedges.
    # Case-specific decision, not a universal rule to remove all disconnected components.
    for group in groups[1:]:
        pts=np.array([v.co[:] for v in group]); faces={f for v in group for f in v.link_faces}
        removed.append({'vertices':len(group),'triangles':len(faces),'center':pts.mean(0).tolist()})
        bmesh.ops.delete(bm,geom=list(group),context='VERTS')
    bm.to_mesh(cat.data); bm.free(); cat.data.update()
if variant in ['flat', 'clean-flat']:
    for face in cat.data.polygons:
        face.use_smooth = False

sc = bpy.context.scene
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
sc.view_settings.exposure = 0
sc.view_settings.gamma = 1
sc.cycles.samples = 32
sc.render.resolution_x = 1200
sc.render.resolution_y = 900
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.film_transparent = False
report = {
    'variant': variant,
    'source': str(source.relative_to(HERE)),
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'purpose': ('Compare manual eye roughness mask with local-color; all other appearance settings identical.' if variant=='eye-material' else 'Compare local color projection with clean-flat; identical geometry, material values, camera and lighting.' if variant=='local-color' else 'Same mesh family, texture, material, camera and lighting; isolate normals and previous uniform subdivision.'),
    'material': {'metallic': 0, 'roughness': .9, 'specular_ior_level': .15},
    'identity_or_art_pass': False,
    'geometry_changed_this_probe': bool(removed),
    'removed_reviewed_detached_components': removed,
    'automatic_cleanup_claim': False,
    'views': [
        {'name':'hero','az':-69,'el':10,'target':[0,0,.20],'scale':.79},
        {'name':'face','az':-69,'el':9,'target':[.23,0,.31],'scale':.28}
    ],
    'stats': mesh_stats(cat)
}
for view in report['views']:
    render(view['name'], view['az'], view['el'], target=view['target'], scale=view['scale'])
    if not texture_probe:
        render(view['name']+'-clay', view['az'], view['el'], target=view['target'], scale=view['scale'], clay=True)
if texture_probe:
    render('opposite',110,10,target=(0,0,.20),scale=.79)
export_npz(cat, OUT / 'mesh.npz')
(OUT / ('render-report.json' if variant=='eye-material' else 'report.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'scene.blend'))
if variant in ['clean-flat', 'local-color', 'eye-material']:
    bpy.ops.object.select_all(action='DESELECT');cat.select_set(True);bpy.context.view_layer.objects.active=cat
    bpy.ops.export_scene.gltf(filepath=str(OUT/'cat.glb'),export_format='GLB',use_selection=True)
print('PROBE_COMPLETE', variant, flush=True)
