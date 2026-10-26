"""Lossless clip selection: all retained curves and the BIN chunk stay identical."""
import hashlib
import json
from pathlib import Path
import struct

P=Path(__file__).resolve().parent
source=P.parent/'27-animation-compatibility/weights-v001/export/cat-animated.glb'
raw=source.read_bytes();magic,version,total=struct.unpack_from('<III',raw)
assert magic==0x46546C67 and version==2 and total==len(raw)
chunks=[];pos=12
while pos<len(raw):
    length,kind=struct.unpack_from('<II',raw,pos);pos+=8
    chunks.append((kind,raw[pos:pos+length]));pos+=length
assert chunks[0][0]==0x4E4F534A
original=json.loads(chunks[0][1]);doc=json.loads(chunks[0][1])
keep=['Walk','Idle_to_Sit','Sitting','Sitting_to_Idle']
byname={a['name']:a for a in doc['animations']}
assert set(keep)<=set(byname)
doc['animations']=[byname[name] for name in keep]
js=json.dumps(doc,separators=(',',':'),ensure_ascii=False).encode();js+=b' '*((-len(js))%4)
body=struct.pack('<II',len(js),chunks[0][0])+js
for kind,data in chunks[1:]:body+=struct.pack('<II',len(data),kind)+data
result=struct.pack('<III',magic,version,12+len(body))+body
out=P/'cat-walk-sit.glb'
if out.exists():raise RuntimeError('Preserve selected pack')
out.write_bytes(result)
assert {k:v for k,v in original.items() if k!='animations'}=={k:v for k,v in doc.items() if k!='animations'}
assert all(a==byname[a['name']] for a in doc['animations'])
triangles=sum(doc['accessors'][p['indices']]['count']//3 for m in doc['meshes'] for p in m['primitives'])
assert triangles==3500 and len(doc['skins'][0]['joints'])==56
report={
 'source':str(source),'source_sha256':hashlib.sha256(raw).hexdigest(),
 'output':out.name,'output_sha256':hashlib.sha256(result).hexdigest(),
 'user_visible_behaviors':['Walk','Sitting'],'clips':keep,
 'supporting_transitions':['Idle_to_Sit','Sitting_to_Idle'],
 'removed_clip':'Idle','triangles':triangles,'bones':56,
 'binary_chunks_unchanged':True,'retained_animation_channels_unchanged':True,
 'other_gltf_metadata_unchanged':True,
 'packing_note':'Unreferenced Idle buffers remain in BIN to preserve byte-identical geometry/material/skin/curve data; file-size compaction is not claimed.',
 'animation_quality_pass':False,'new_cat_automation_proven':False,'unity_pass':False,
 'known_limitations':['Previous stage 27 contact/stretch defects remain; selection does not repair them.',
   'Walking is in-place; world travel, stop/start blending and support-phase transitions are not configured or tested in Unity.',
   'Two behaviors need supporting sit-down/stand-up transitions. Four clips are not four requested user behaviors.'],
}
(P/'selection.json').write_text(json.dumps(report,indent=2)+'\n')
(P/'executed-selection-source.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'clips':keep,'triangles':triangles,'binary_unchanged':True}),flush=True)
