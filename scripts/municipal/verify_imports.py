"""Read-only Atlas audit of the four municipal batches through backend storage APIs."""
from __future__ import annotations
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def main():
 p=argparse.ArgumentParser();p.add_argument('--api-root',default=str(ROOT/'services/api'));p.add_argument('--env-file',default=str(Path.home()/'.config/ontara/mongodb.env'));p.add_argument('--output',default=str(ROOT/'data/municipal/atlas_verification.json'));a=p.parse_args()
 sys.path.insert(0,a.api_root)
 from app.config import Settings
 from app.storage import Store,ArtifactStore
 from app.models import ResearchBatch
 batches=[ResearchBatch.model_validate_json(x.read_text()).model_dump(by_alias=True,mode='json') for x in sorted((ROOT/'data/municipal').glob('roads-batch-0[1-4]-20261114.import.json'))]
 assert len(batches)==4,'Expected four batches'
 expected={key:{v['id']:v for b in batches for v in b[key]} for key in ['municipalities','sources','procedures','formSnapshots','artifacts']}
 store=Store.connect(Settings.load(a.env_file));db=store.db;files=ArtifactStore(db)
 errors=[]
 def records(collection,key):
  rows={r['id']:r for r in db[collection].find({'id':{'$in':list(expected[key])}})}
  if set(rows)!=set(expected[key]):errors.append('Missing '+collection+' records')
  return rows
 municipalities=records('municipalities','municipalities');sources=records('source_references','sources');procedures=records('service_procedures','procedures');forms=records('form_snapshots','formSnapshots');artifacts=records('artifacts','artifacts')
 for mid,ex in expected['municipalities'].items():
  row=municipalities.get(mid,{})
  for key in ['type','parentId','population','populationYear','memberIds']:
   if row.get(key)!=ex.get(key):errors.append(mid+': '+key+' differs')
 for sid,ex in expected['sources'].items():
  row=sources.get(sid,{})
  if row.get('sourceVersion')!=ex['sourceVersion']:errors.append(sid+': source version differs')
  if hashlib.sha256(row.get('extractedText','').encode()).hexdigest()!=row.get('contentHash'):errors.append(sid+': text hash differs')
 for pid,ex in expected['procedures'].items():
  row=procedures.get(pid,{})
  for key in ['sourceVersion','authorityId','issueIds','verificationStatus','visibility','current','integrationStatus']:
   if row.get(key)!=ex.get(key):errors.append(pid+': '+key+' differs')
  if ex['verificationStatus']=='verified' and row.get('searchStatus')!='ready':errors.append(pid+': native search not ready')
 for fid,ex in expected['formSnapshots'].items():
  row=forms.get(fid,{})
  if row.get('sourceVersion')!=ex['sourceVersion'] or row.get('fields')!=ex.get('fields',[]):errors.append(fid+': snapshot differs')
 for aid,ex in expected['artifacts'].items():
  row=artifacts.get(aid,{})
  if row.get('status')!='ready' or row.get('sha256')!=ex['expectedSha256']:errors.append(aid+': artifact not ready/hash mismatch')
 runs=[]
 coverage=[]
 for b in batches:
  row=db.import_runs.find_one({'id':b['batchId']},{'_id':0})
  if not row or row.get('status')!='completed' or row.get('searchStatus')!='ready':errors.append(b['batchId']+': import/search gate not complete')
  if row and row.get('coverage')!=b['coverage']:errors.append(b['batchId']+': coverage differs')
  runs.append({'batchId':b['batchId'],'status':row.get('status') if row else None,'searchStatus':row.get('searchStatus') if row else None,'authorities':len([m for m in b['municipalities'] if m['type']=='upper-tier']),'counts':row.get('counts') if row else None})
  coverage+=b['coverage']
 pairs={(c['authorityId'],c['issueId']) for c in coverage};assert len(pairs)==160
 kind_counts={k:sum(c.get('coverageKind')==k for c in coverage) for k in sorted({c.get('coverageKind') for c in coverage})}
 samples=[]
 for b in batches:
  ex=next(v for v in b['artifacts'] if v['mimeType']=='text/html')
  content=files.read(ex['id']);digest=hashlib.sha256(content).hexdigest()
  if digest!=ex['expectedSha256']:errors.append(ex['id']+': fresh process read hash mismatch')
  samples.append({'artifactId':ex['id'],'byteCount':len(content),'sha256':digest,'freshProcessRead':'passed'})
 pop=next(v for v in batches[0]['artifacts'] if v['id'].startswith('statcan-'))
 content=files.read(pop['id']);assert hashlib.sha256(content).hexdigest()==pop['expectedSha256'];samples.append({'artifactId':pop['id'],'byteCount':len(content),'sha256':pop['expectedSha256'],'freshProcessRead':'passed'})
 report={'verifiedAt':datetime.now(timezone.utc).isoformat(),'status':'passed' if not errors else 'failed','scope':'Four Roads-only municipal research batches; read-only checks of expected IDs, not a claim of live municipal integration.','counts':{'upperTiers':sum(m['type']=='upper-tier' for m in municipalities.values()),'supportingLowerTiers':sum(m['type']=='lower-tier' for m in municipalities.values()),'procedures':len(procedures),'verifiedSearchableProcedures':sum(r.get('verificationStatus')=='verified' and r.get('searchStatus')=='ready' for r in procedures.values()),'partialProcedures':sum(r.get('verificationStatus')=='partial' for r in procedures.values()),'sourceReferences':len(sources),'unavailableSources':sum(r.get('verificationStatus')=='unavailable' for r in sources.values()),'readyArtifacts':sum(r.get('status')=='ready' for r in artifacts.values()),'formSnapshots':len(forms),'coverageCells':len(pairs),'coverageKinds':kind_counts},'batches':runs,'freshProcessArtifactReads':samples,'errors':errors}
 Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'counts':report['counts'],'errorCount':len(errors),'output':a.output}))
 return 1 if errors else 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:
  print(json.dumps({'status':'failed','errorType':type(exc).__name__}),file=sys.stderr);raise SystemExit(1)
