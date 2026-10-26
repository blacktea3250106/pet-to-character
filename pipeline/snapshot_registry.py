"""Validate issue/event references and preserve an immutable audit-time hash snapshot.

This records provenance, not historical executed code versions or art acceptance.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
P=Path(__file__).resolve().parent;WORKSPACE=P.parents[1]
review=json.loads((P/'automation-review.json').read_text());history=json.loads((P/'experiment-history.json').read_text())
ids={x['id'] for x in review['issues']};assert len(ids)==len(review['issues'])
paths={'automation-review.json','experiment-history.json','snapshot_registry.py'}
for issue in review['issues']:
    for key in ['problem','current_fix','automation_status','future_detection','future_repair','validation','risk']:assert issue[key],(issue['id'],key)
    paths.update(issue['evidence'])
for event in history['events']:
    assert set(event['issues'])<=ids,event['id']
    assert event['new_cat_automation_proven'] is False,'Current single-cat case cannot establish unseen-cat success'
    paths.update(event['inputs']);paths.update(event['outputs'])
    paths.update(event.get('additional_scripts',[]))
    if event['script']:paths.add(event['script'])
files=[]
for item in sorted(paths):
    path=(P/item).resolve();assert path.is_relative_to(WORKSPACE) and path.is_file(),item
    files.append({'path':item,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size})
now=datetime.now(timezone.utc)
snapshot={'captured_at':now.isoformat(),'meaning':'Current artifacts and code at audit time; does not reconstruct unknown past revisions','issue_count':len(ids),'event_count':len(history['events']),'files':files,'art_or_automation_acceptance':False}
out=P/'automation-evidence'/('registry-snapshot-'+now.strftime('%Y%m%dT%H%M%S%fZ')+'.json')
out.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
print(json.dumps({'snapshot':str(out.relative_to(P)),'issues':len(ids),'events':len(history['events']),'hashed_files':len(files)},ensure_ascii=False))
