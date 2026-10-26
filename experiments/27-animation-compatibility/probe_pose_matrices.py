from pathlib import Path
import json
import bpy
import numpy as np
P=Path(__file__).resolve().parent
out=P/'baseline-v001'
r=json.loads((out/'report.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(out/'animated.blend'))
src=bpy.data.objects[r['source_rig']]; rig=bpy.data.objects[r['target_rig']]
C=np.array(r['canonical_rotation']); scale=np.array(r['scale']); offset=np.array(r['offset'])
rows=[]
for name,frame in [('Idle',1),('Walk',7),('Sitting',1)]:
 a=next(a for a in bpy.data.actions if '|' in a.name and a.name.split('|')[-1]==name)
 src.animation_data.action=a;src.animation_data.action_slot=a.slots[0]
 a=bpy.data.actions[name];rig.animation_data.action=a;rig.animation_data.action_slot=a.slots[0]
 bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
 for bn in ['root','DEF-spine','DEF-spine.003','DEF-hand.L','DEF-f_toe.L','DEF-r_toe.L','DEF-tail.004']:
  s=src.pose.bones[bn];t=rig.pose.bones[bn]
  want=C@np.array(src.matrix_world@s.head)*scale+offset
  got=np.array(rig.matrix_world@t.head)
  rows.append({'action':name,'frame':frame,'bone':bn,'desired_affine_head':want.tolist(),'actual_head':got.tolist(),'distance':float(np.linalg.norm(want-got)),
               'source_basis_location':list(s.location),'target_basis_location':list(t.location),'source_basis_scale':list(s.scale),'target_basis_scale':list(t.scale),
               'source_rest':list(src.matrix_world@src.data.bones[bn].head_local),'target_rest':list(rig.matrix_world@rig.data.bones[bn].head_local)})
(out/'matrix-probe.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps([{'action':r['action'],'bone':r['bone'],'distance':r['distance'],'want_z':r['desired_affine_head'][2],'got_z':r['actual_head'][2]} for r in rows]))
