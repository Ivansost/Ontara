"""Read-only fresh-process verification of the supplementary Atlas geometry/files."""
from __future__ import annotations
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--api-root',default=str(ROOT/'services/api'));p.add_argument('--env-file',default=str(Path.home()/'.config/ontara/mongodb.env'));a=p.parse_args();sys.path.insert(0,a.api_root)
 from app.config import Settings
 from app.storage import Store,ArtifactStore
 from app.models import ResearchBatch
 batch=ResearchBatch.model_validate_json((ROOT/'data/municipal/roads-boundaries-20261114.import.json').read_text()).model_dump(by_alias=True,mode='json')
 store=Store.connect(Settings.load(a.env_file));db=store.db;files=ArtifactStore(db);errors=[]
 ms={m['id']:m for m in db.municipalities.find({'id':{'$in':[m['id'] for m in batch['municipalities']]}},{'_id':0})}
 for expected in batch['municipalities']:
  actual=ms.get(expected['id'],{})
  for key in ['type','parentId','sourceVersion','boundary','sourceIds','population','populationYear']:
   if actual.get(key)!=expected.get(key):errors.append(expected['id']+': '+key+' differs')
 ss={s['id']:s for s in db.source_references.find({'id':{'$in':[s['id'] for s in batch['sources']]}},{'_id':0})}
 for ex in batch['sources']:
  actual=ss.get(ex['id'],{})
  if actual.get('sourceVersion')!=ex['sourceVersion'] or hashlib.sha256(actual.get('extractedText','').encode()).hexdigest()!=ex['contentHash']:errors.append(ex['id']+': source version/text hash differs')
 reads=[]
 for ex in batch['artifacts']:
  meta=files.get_metadata(ex['id']);content=files.read(ex['id']);digest=hashlib.sha256(content).hexdigest()
  if not meta or meta.get('status')!='ready' or digest!=ex['expectedSha256']:errors.append(ex['id']+': stored file/hash mismatch')
  if ex['mimeType']=='application/pdf' and not (content.startswith(b'%PDF-') and b'%%EOF' in content[-2048:]):errors.append(ex['id']+': invalid PDF markers')
  reads.append({'artifactId':ex['id'],'mimeType':ex['mimeType'],'byteCount':len(content),'sha256':digest,'freshProcessRead':'passed'})
 run=db.import_runs.find_one({'id':batch['batchId']},{'_id':0,'id':1,'status':1,'counts':1})
 if not run or run.get('status')!='completed':errors.append('Boundary import not completed')
 result={'verifiedAt':datetime.now(timezone.utc).isoformat(),'status':'passed' if not errors else 'failed','batchId':batch['batchId'],'counts':{'upperTiers':sum(m['type']=='upper-tier' for m in ms.values()),'lowerTiers':sum(m['type']=='lower-tier' for m in ms.values()),'singleTiers':sum(m['type']=='single-tier' for m in ms.values()),'sources':len(ss),'freshProcessArtifactReads':len(reads)},'importRun':run,'allSingleTierParentsNull':all(m.get('parentId') is None for m in ms.values() if m['type']=='single-tier'),'searchGate':'Not applicable: supplementary geometry/source run writes zero service procedures; four core search-ready runs remain authoritative.','runtimeResolverClaimed':False,'artifactReads':reads,'errors':errors}
 path=ROOT/'data/municipal/boundary_atlas_verification.json';path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'counts':result['counts'],'errorCount':len(errors)}));return bool(errors)
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:print(json.dumps({'status':'failed','errorType':type(exc).__name__}),file=sys.stderr);raise SystemExit(1)
