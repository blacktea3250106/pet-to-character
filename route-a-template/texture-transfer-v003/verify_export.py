"""Check the actual exported GLB, not just the Blender material configuration."""
from pathlib import Path
import json,struct
P=Path(__file__).resolve().parent
raw=(P/'face-color-test.glb').read_bytes()
magic,version,total=struct.unpack_from('<4sII',raw)
assert magic==b'glTF' and version==2 and total==len(raw)
jlen,jtype=struct.unpack_from('<II',raw,12)
g=json.loads(raw[20:20+jlen])
blen,btype=struct.unpack_from('<II',raw,20+jlen)
binary=raw[28+jlen:28+jlen+blen]
components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
formats={5120:'b',5121:'B',5122:'h',5123:'H',5125:'I',5126:'f'}
def accessor(index):
    a=g['accessors'][index];v=g['bufferViews'][a['bufferView']]
    f='<'+formats[a['componentType']]*components[a['type']]
    start=v.get('byteOffset',0)+a.get('byteOffset',0)
    stride=v.get('byteStride',struct.calcsize(f))
    return [struct.unpack_from(f,binary,start+i*stride) for i in range(a['count'])]
count=0;bad=0;max_influences=0
for m in g['meshes']:
    for primitive in m['primitives']:
        attr=primitive['attributes'];assert 'COLOR_0' in attr
        colors=accessor(attr['COLOR_0']);ids=[x[0] for x in accessor(primitive['indices'])]
        assert len(ids)%3==0
        for a,b,c in zip(ids[::3],ids[1::3],ids[2::3]):
            count+=1;bad+=int(not(colors[a]==colors[b]==colors[c]))
        weightsets=[accessor(v) for k,v in attr.items() if k.startswith('WEIGHTS_')]
        for rows in zip(*weightsets):max_influences=max(max_influences,sum(x>0 for row in rows for x in row))
assert count==2144 and bad==0
assert not g.get('images') and not g.get('textures')
result={'triangles':count,'nonconstant_color_triangles':bad,'image_textures':0,
        'max_exported_skin_influences':max_influences,'animation_clips':len(g.get('animations',[])),
        'status':'pass'}
(P/'export-validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
