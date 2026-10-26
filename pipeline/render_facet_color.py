"""Apply color-only variants to a fixed scene and render/export isolated copies."""
import ast
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
import bpy
import bmesh
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
cfg_path = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
cfg = json.loads(cfg_path.read_text())
source = HERE / cfg['source']
root = HERE / cfg['output']
source_report = json.loads((source / 'render-report.json').read_text())
source_mesh = np.load(source / 'mesh.npz')
helper = (HERE / 'blender_stage.py').read_bytes()
tree = ast.parse(helper)
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'bsdf', 'make_mat', 'render', 'export_npz', 'mesh_stats'}], type_ignores=[]), 'render_helpers', 'exec'))
(root / 'executed-render-source.py').write_bytes(Path(__file__).read_bytes())


def emission_views(cat):
    original = cat.data.materials[0]
    material = original.copy()
    material.name = 'DiagnosticBaseColorOnly'
    node = bsdf(material)
    links = node.inputs['Base Color'].links
    assert len(links) == 1
    tex = links[0].from_node
    assert tex.type == 'TEX_IMAGE'
    nt = material.node_tree
    emission = nt.nodes.new('ShaderNodeEmission')
    nt.links.new(tex.outputs['Color'], emission.inputs['Color'])
    emission.inputs['Strength'].default_value = 1
    output = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
    nt.links.new(emission.outputs[0], output.inputs['Surface'])
    cat.data.materials[0] = material
    for name, az, el, target, scale in source_report['views'][:2]:
        render(name + '-base-color', az, el, target=target, scale=scale)
    cat.data.materials[0] = original


# Fixed baseline uses the same temporary emission material as the variants.
OUT = root / 'baseline'
OUT.mkdir(exist_ok=False)
bpy.ops.wm.open_mainfile(filepath=str(source / 'scene.blend'))
emission_views(bpy.data.objects['Cat'])

for variant in cfg['variants']:
    OUT = root / variant['id']
    if (OUT / 'scene.blend').exists():
        raise FileExistsError('Preserve prior variant scene')
    bpy.ops.wm.open_mainfile(filepath=str(source / 'scene.blend'))
    cat = bpy.data.objects['Cat']
    assert len(cat.data.materials) == 1
    material = cat.data.materials[0].copy()
    cat.data.materials[0] = material
    tex = bsdf(material).inputs['Base Color'].links[0].from_node
    assert tex.type == 'TEX_IMAGE'
    tex.image = bpy.data.images.load(str(OUT / 'base-color.png'), check_existing=False)
    tex.image.colorspace_settings.name = 'sRGB'
    export_npz(cat, OUT / 'mesh.npz')
    result = np.load(OUT / 'mesh.npz')
    identical = {key: bool(np.array_equal(source_mesh[key], result[key])) for key in source_mesh.files}
    assert all(identical.values()), identical
    stats = mesh_stats(cat)
    assert stats['triangles'] == cfg['required_triangles']
    shutil.copy2(source / 'roughness.png', OUT / 'roughness.png')
    report = {'stage': 'Bounded per-face color simplification on fixed mesh', 'variant': variant,
              'inputs': [{'path': str(p.relative_to(HERE)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in [source / 'scene.blend', source / 'mesh.npz', source / 'render-report.json', OUT / 'base-color.png', OUT / 'processing-report.json']],
              'geometry_uv_material_ids_equal_to_source': identical, 'stats': stats,
              'views': source_report['views'], 'source': cfg['source'],
              'shader_settings_changed': False, 'geometry_changed': False,
              'camera_and_lights_changed': False, 'new_manual_regions': [],
              'identity_or_art_pass': False, 'animation_validation': False,
              'unity_validation': False, 'new_cat_automation_proven': False}
    (OUT / 'render-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'scene.blend'))
    bpy.ops.object.select_all(action='DESELECT')
    cat.select_set(True)
    bpy.context.view_layer.objects.active = cat
    bpy.ops.export_scene.gltf(filepath=str(OUT / 'cat.glb'), export_format='GLB', use_selection=True)
    for name, az, el, target, scale in source_report['views']:
        render(name, az, el, target=target, scale=scale)
    emission_views(cat)
    print('FACET_COLOR_VARIANT_RENDERED', variant['id'], json.dumps(identical), flush=True)
