import bpy,json,numpy as np
from pathlib import Path
P=Path('experiments/generation-v001/27-animation-compatibility')
r=json.loads((P/'baseline-v001/report.json').read_text());bpy.ops.wm.open_mainfile(filepath=str(P/'baseline-v001/rigged-rest.blend'))
s=bpy.data.objects[r['source_rig']];t=bpy.data.objects[r['target_rig']];C=np.array(r['canonical_rotation'])
for name in ['root','DEF-spine','DEF-hand.L']:
 a=s.data.bones[name];b=t.data.bones[name]
 print(json.dumps({'bone':name,'src_flags':{k:getattr(a,k) for k in ['use_local_location','use_inherit_rotation','inherit_scale','use_relative_parent']},'tgt_flags':{k:getattr(b,k) for k in ['use_local_location','use_inherit_rotation','inherit_scale','use_relative_parent']},'rotation_error':float(np.max(np.abs(C@np.array((s.matrix_world@a.matrix_local).to_3x3())-np.array(b.matrix_local.to_3x3())))),'source_R':(C@np.array((s.matrix_world@a.matrix_local).to_3x3())).tolist(),'target_R':np.array(b.matrix_local.to_3x3()).tolist()}))
