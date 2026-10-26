"""Conservative research gate: new foldovers or missing evidence require review.

Added after stage 28 exposed missing pre-bind validation; not a retrospective gate.
"""
import json
from pathlib import Path

P=Path(__file__).resolve().parent
for folder in sorted((P/'fit-v002').iterdir()):
    if not (folder/'rest-audit.json').exists():continue
    audit=json.loads((folder/'rest-audit.json').read_text())
    reasons=[]
    if audit['new_scaffold_crossing_pairs']:
        reasons.append('New nonadjacent scaffold crossings require review before production binding.')
    if audit['target_rest_crossing_pairs']:
        reasons.append('Target rest geometry has detected self crossings.')
    tail=[j['retained_axis_vs_mapped_bone_degrees'] for j in audit['joints'] if 'tail.' in j['bone']]
    if max(tail)>30:
        reasons.append('Retained tail axes differ materially from mapped directions; rest-pose retargeting must be validated.')
    result={'case':folder.name,'timing':'added_after_experiment_for_future_runs',
            'status':'needs_review','production_binding_allowed':False,
            'reasons':reasons or ['Anatomical and animation acceptance has not been established.'],
            'new_scaffold_crossing_pairs':audit['new_scaffold_crossing_pairs'],
            'tail_axis_max_degrees':max(tail),
            'threshold_note':'30 degrees is a conservative research warning, not a calibrated support boundary. New crossing counts require interpretation, not a production success metric.',
            'original_runs':'Existing candidate bind/animation outputs were diagnostic experiments before this gate was added; not claimed pre-approved.',
            'new_cat_automation_proven':False}
    (folder/'fit-gate.json').write_text(json.dumps(result,indent=2)+'\n')
print('FUTURE_BIND_GATES_RECORDED')
