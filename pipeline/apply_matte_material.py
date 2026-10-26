"""Create a material-only GLB candidate while preserving all binary data.

Reject unsupported multi-material or optical setups instead of guessing roles.
"""
import argparse
import copy
import hashlib
import json
import math
import struct
from pathlib import Path

from glb_preflight import inspect_glb

EXT = 'KHR_materials_specular'

def read_glb(path):
    blob = path.read_bytes()
    magic, version, total = struct.unpack_from('<4sII', blob)
    if (magic, version, total) != (b'glTF', 2, len(blob)):
        raise ValueError('Invalid GLB header')
    offset, chunks = 12, []
    while offset < len(blob):
        size, kind = struct.unpack_from('<II', blob, offset)
        if size % 4 or offset + 8 + size > len(blob):
            raise ValueError('Invalid chunk boundary')
        chunks.append((kind, blob[offset + 8:offset + 8 + size]))
        offset += 8 + size
    if [kind for kind, _ in chunks] != [0x4E4F534A, 0x004E4942]:
        raise ValueError('Only JSON + embedded BIN GLBs supported')
    return json.loads(chunks[0][1]), chunks[1][1]

def write_glb(path, document, binary):
    data = json.dumps(document, ensure_ascii=False, separators=(',', ':')).encode()
    data += b' ' * (-len(data) % 4)
    body = struct.pack('<II', len(data), 0x4E4F534A) + data
    body += struct.pack('<II', len(binary), 0x004E4942) + binary
    path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12 + len(body)) + body)

parser = argparse.ArgumentParser()
parser.add_argument('profile', type=Path)
parser.add_argument('--output', type=Path, help='Fresh output directory; profile values remain unchanged')
args = parser.parse_args()
root = Path(__file__).resolve().parent
profile = json.loads(args.profile.read_text())
source = root / profile['source']
out = args.output.resolve() if args.output else root / profile['output']
factor = profile['specular_factor']
if not isinstance(factor, (float, int)) or not math.isfinite(factor) or not 0 <= factor <= 1:
    raise ValueError('Invalid specular factor')
if out.exists():
    raise RuntimeError('Use a new immutable candidate output directory')
doc, binary = read_glb(source)
before = copy.deepcopy(doc)
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
if len(doc.get('materials', [])) != 1:
    raise ValueError('Multiple material roles require semantic assignments first')
mat = doc['materials'][0]
pbr = mat.get('pbrMetallicRoughness', {})
if pbr.get('metallicFactor', 1) != 0 or 'metallicRoughnessTexture' in pbr:
    raise ValueError('Only non-metallic scalar materials supported')
if mat.get('alphaMode', 'OPAQUE') != 'OPAQUE':
    raise ValueError('Transparent materials require a separate policy')
extensions = mat.get('extensions', {})
if set(extensions) - {EXT}:
    raise ValueError('Unsupported optical material extension')
old_specular = extensions.get(EXT, {})
if set(old_specular) - {'specularFactor'}:
    raise ValueError('Specular maps/colors require separate handling')
mat.setdefault('extensions', {})[EXT] = {'specularFactor': factor}
used = doc.setdefault('extensionsUsed', [])
if EXT not in used:
    used.append(EXT)

out.mkdir(parents=True)
candidate = out / 'cat.glb'
write_glb(candidate, doc, binary)
after, new_binary = read_glb(candidate)
# Undo only the authorized material edit to prove there are no other JSON changes.
restored = copy.deepcopy(after)
if EXT in before['materials'][0].get('extensions', {}):
    restored['materials'][0]['extensions'][EXT] = before['materials'][0]['extensions'][EXT]
else:
    del restored['materials'][0]['extensions'][EXT]
    if not restored['materials'][0]['extensions'] and 'extensions' not in before['materials'][0]:
        del restored['materials'][0]['extensions']
if EXT not in before.get('extensionsUsed', []):
    restored['extensionsUsed'].remove(EXT)
    if not restored['extensionsUsed'] and 'extensionsUsed' not in before:
        del restored['extensionsUsed']
report = {
    'source_sha256': source_hash,
    'candidate_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
    'previous_specular_factor': old_specular.get('specularFactor', 1),
    'candidate_specular_factor': factor,
    'all_binary_data_identical': binary == new_binary,
    'all_other_json_fields_identical': before == restored,
    'source_file_unchanged': hashlib.sha256(source.read_bytes()).hexdigest() == source_hash,
    'binary_sha256': hashlib.sha256(binary).hexdigest(),
    'meaning': 'Geometry, UVs, normals, textures and their bindings are byte-identical; only specular factor and extension declaration change.',
    'scope': 'Provisional single-surface material preset. No coat recolor, eye-specific treatment, topology edits or rigging.',
    'blender_import_verified': False, 'unity_verified': False,
    'asset_accepted': False, 'new_cat_automation_proven': False
}
assert all(report[k] for k in ('all_binary_data_identical', 'all_other_json_fields_identical', 'source_file_unchanged'))
(out / 'change-report.json').write_text(json.dumps(report, indent=2) + '\n')
(out / 'preflight.json').write_text(json.dumps(inspect_glb(candidate, 3500), indent=2) + '\n')
(out / 'executed-source.py').write_bytes(Path(__file__).read_bytes())
(out / 'executed-preflight.py').write_bytes((root / 'glb_preflight.py').read_bytes())
(out / 'executed-profile.json').write_bytes(args.profile.read_bytes())
print(json.dumps({'all_binary_data_identical': report['all_binary_data_identical'],
                  'all_other_json_fields_identical': report['all_other_json_fields_identical'],
                  'specular_factor': factor, 'candidate_sha256': report['candidate_sha256']}))
