"""Blender-only material isolation on an existing, provenance-bound review scene.

No asset export, repainting, per-cat masks, or anatomical assumptions.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

parser = argparse.ArgumentParser()
parser.add_argument('config', type=Path)
parser.add_argument('--output', type=Path, help='Fresh output directory for independent reproduction')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
root = Path(__file__).resolve().parent
config = json.loads(args.config.read_text())
source = root / config['source']
scene_file = root / config['scene']
scene_report = json.loads((root / config['scene_report']).read_text())
out = args.output.resolve() if args.output else root / config['output']
if out.exists():
    raise RuntimeError('Use a new output directory; diagnostics are immutable')
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
source_hash, scene_hash = digest(source), digest(scene_file)
if source_hash != scene_report['source_sha256']:
    raise RuntimeError('Review scene provenance does not match the source asset')
bpy.ops.wm.open_mainfile(filepath=str(scene_file.resolve()))
sc = bpy.context.scene
meshes = [bpy.data.objects[g['name']] for g in scene_report['geometry']]
if any(o.type != 'MESH' for o in meshes):
    raise RuntimeError('Expected review mesh objects')
ground = bpy.data.objects.get('ReviewGround')
if ground is None or sc.camera is None:
    raise RuntimeError('Not a supported generic review scene')

def mesh_state():
    h = hashlib.sha256()
    for ob in meshes:
        me = ob.data
        me.calc_loop_triangles()
        h.update(np.asarray(ob.matrix_world, dtype='<f8').tobytes())
        h.update(np.array([v.co[:] for v in me.vertices], dtype='<f8').tobytes())
        h.update(np.array([t.vertices[:] for t in me.loop_triangles], dtype='<i8').tobytes())
        h.update(np.array([u.uv[:] for u in me.uv_layers.active.data], dtype='<f8').tobytes())
        h.update(np.array([n.vector[:] for n in me.corner_normals], dtype='<f8').tobytes())
    return h.hexdigest()

geometry_hash = mesh_state()
original_slots = {o.name: list(o.data.materials) for o in meshes}
materials = {m for slots in original_slots.values() for m in slots}
if None in materials:
    raise RuntimeError('Missing source material')
for mat in materials:
    bsdfs = [n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED']
    outputs = [n for n in mat.node_tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output]
    if len(bsdfs) != 1 or len(outputs) != 1:
        raise RuntimeError('Only single Principled surface materials supported')
    bsdf, output = bsdfs[0], outputs[0]
    if len(output.inputs['Surface'].links) != 1 or output.inputs['Surface'].links[0].from_node != bsdf:
        raise RuntimeError('Expected direct Principled surface')
    if bsdf.inputs['Metallic'].is_linked or bsdf.inputs['Metallic'].default_value != 0:
        raise RuntimeError('Dielectric isolation does not cover metallic surfaces')
    if bsdf.inputs['Specular IOR Level'].is_linked:
        raise RuntimeError('Linked specular map needs a separate diagnostic')

out.mkdir(parents=True)
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
(out / 'executed-config.json').write_bytes(args.config.read_bytes())
report = {
    'artifact_kind': 'actual_3D_diagnostic_renders',
    'source': str(source), 'source_sha256': source_hash,
    'review_scene_sha256': scene_hash, 'blender': bpy.app.version_string,
    'config': config, 'mesh_state_before': geometry_hash,
    'render_settings': {'view_transform': sc.view_settings.view_transform,
                        'look': sc.view_settings.look,
                        'exposure': sc.view_settings.exposure,
                        'gamma': sc.view_settings.gamma},
    'modes': {
        'baseline': 'Imported GLB material, unchanged',
        'no_specular': 'Only Principled Specular IOR Level set to 0 over the entire surface; diagnostic, not an eye-material solution',
        'base_color': 'Base Color socket drives strength-1 emission only for camera rays; other rays retain original BSDF'
    },
    'renders': [], 'asset_modified': False,
    'identity_or_art_pass': False, 'new_cat_automation_proven': False
}
sc.cycles.samples = config['cycles_samples']
sc.cycles.seed = config['cycles_seed']
sc.cycles.use_animated_seed = False
pts = np.array([ob.matrix_world @ v.co for ob in meshes for v in ob.data.vertices])
center = Vector((pts.min(0) + pts.max(0)) / 2)
diagonal = float(np.linalg.norm(np.ptp(pts, axis=0)))
sc.camera.data.ortho_scale = diagonal * 1.08

variants = {'baseline': {m: m for m in materials}}
for mode in ('no_specular', 'base_color'):
    variants[mode] = {}
    for original in materials:
        mat = original.copy()
        mat.name = original.name + '_' + mode
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
        if mode == 'no_specular':
            bsdf.inputs['Specular IOR Level'].default_value = 0
        else:
            output = next(n for n in nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
            emission = nodes.new('ShaderNodeEmission')
            emission.inputs['Strength'].default_value = 1
            base = bsdf.inputs['Base Color']
            if base.is_linked:
                links.new(base.links[0].from_socket, emission.inputs['Color'])
            else:
                emission.inputs['Color'].default_value = base.default_value
            mix = nodes.new('ShaderNodeMixShader')
            light_path = nodes.new('ShaderNodeLightPath')
            links.new(light_path.outputs['Is Camera Ray'], mix.inputs[0])
            links.new(bsdf.outputs['BSDF'], mix.inputs[1])
            links.new(emission.outputs[0], mix.inputs[2])
            links.new(mix.outputs[0], output.inputs['Surface'])
        variants[mode][original] = mat

def set_mode(mode):
    for ob in meshes:
        for i, original in enumerate(original_slots[ob.name]):
            ob.data.materials[i] = variants[mode][original]

for az in config['views']:
    angle, elevation = math.radians(az), math.radians(config['elevation_degrees'])
    direction = Vector((math.cos(angle) * math.cos(elevation), math.sin(angle) * math.cos(elevation), math.sin(elevation)))
    sc.camera.location = center + direction * max(diagonal * 3, 2)
    sc.camera.rotation_euler = (center - sc.camera.location).to_track_quat('-Z', 'Y').to_euler()
    for mode in config['modes']:
        set_mode(mode)
        filename = f'{mode}-az{az % 360:03d}.png'
        sc.render.filepath = str((out / filename).resolve())
        bpy.ops.render.render(write_still=True)
        report['renders'].append({'file': filename, 'azimuth': az, 'mode': mode})
    # Alpha comes from the complete mesh in this camera; no semantic segmentation.
    set_mode('baseline')
    ground.hide_render = True
    sc.render.film_transparent = True
    filename = f'alpha-source-az{az % 360:03d}.png'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.filepath = str((out / filename).resolve())
    bpy.ops.render.render(write_still=True)
    ground.hide_render = False
    sc.render.film_transparent = False
    report['renders'].append({'file': filename, 'azimuth': az, 'mode': 'alpha_source',
                              'scope': 'Only alpha used; hiding the ground changes indirect lighting in this diagnostic RGB'})
set_mode('baseline')
report['mesh_state_after'] = mesh_state()
report['source_file_unchanged'] = digest(source) == source_hash
report['review_scene_file_unchanged'] = digest(scene_file) == scene_hash
report['geometry_uv_normals_unchanged'] = geometry_hash == report['mesh_state_after']
assert all(report[k] for k in ['source_file_unchanged', 'review_scene_file_unchanged', 'geometry_uv_normals_unchanged'])
(out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print('APPEARANCE_DIAGNOSTIC_COMPLETE', json.dumps({'renders': len(report['renders']), 'source_unchanged': True}), flush=True)
