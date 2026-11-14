"""Build backend ResearchBatch payloads. Source artifacts excluded from Git, retained in Atlas."""
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from source_tools import ROOT,CACHE,capture,artifact
from rank_upper_tiers import REGISTRY_SOURCE,POP_SOURCE,POP_URL

ISSUES=['roads-pothole','roads-pavement','roads-debris-loose','roads-debris-object','roads-sidewalk','roads-curb','roads-sign','roads-safety']

def build(authority_ids,batch_id,include_population=False):
 ranking=json.loads((ROOT/'data/municipal/population_ranking_2021.json').read_text())
 curated=json.loads((ROOT/'data/municipal/roads_authorities.json').read_text())
 rankmap={a['id']:a for a in ranking['upperTiers']}
 batch={'schemaVersion':'1.0','batchId':batch_id,'municipalities':[],'sources':[],'procedures':[],'formSnapshots':[],'artifacts':[],'coverage':[],'gaps':[]}
 seen_sources=set();seen_munis=set()
 for aid in authority_ids:
  spec=next(x for x in curated if x['authorityId']==aid);u=rankmap[aid]
  municipalities=[{'id':aid,'name':u['fullName'],'type':'upper-tier','memberIds':[m['id'] for m in u['members']],'officialUrl':u['officialUrl'],'population':u['population2021'],'populationYear':2021,'populationSourceIds':[REGISTRY_SOURCE,POP_SOURCE],'selectionRank':u['rank'],'sourceIds':[s['id'] for s in spec['sources']],'sourceVersion':'2021-members-2026-registry-v1'}]
  municipalities += [{'id':m['id'],'name':m['fullName'],'type':'lower-tier','parentId':aid,'officialUrl':m['officialUrl'],'population':m['population2021'],'populationYear':2021,'populationSourceIds':[REGISTRY_SOURCE,POP_SOURCE],'sourceIds':[REGISTRY_SOURCE],'sourceVersion':'2021-csd-v1'} for m in u['members']]
  for m in municipalities:
   if m['id'] not in seen_munis: batch['municipalities'].append(m);seen_munis.add(m['id'])
  metas={s['id']:capture(s['id'],aid,s['url'],s.get('title'),allow_error=s.get('allowUnavailable',False)) for s in spec['sources']}
  for sid,meta in metas.items():
   if sid not in seen_sources:
    batch['sources'].append(meta['source'])
    if meta.get('rawPath'):batch['artifacts'].append(artifact(meta))
    seen_sources.add(sid)
  for p in spec['procedures']:
   p=p.copy();key=p.pop('key');source_ids=p['sourceIds']
   version=hashlib.sha256((json.dumps({'procedure':p,'formSnapshots':[f for f in spec.get('formSnapshots',[]) if f['procedureKey']==key]},sort_keys=True,ensure_ascii=False)+'|'+'|'.join(metas[s]['source']['sourceVersion'] for s in source_ids)).encode()).hexdigest()[:16]
   p.update(id=aid+'-'+key,authorityId=aid,categoryId='roads',sourceVersion=version,visibility='public',current=True,integrationStatus='research_only',searchStatus='pending',verifiedAt=max(metas[s]['source']['verifiedAt'] for s in source_ids))
   p.setdefault('verificationStatus','verified');p.setdefault('researchStatus','verified')
   p['artifactIds']=[a for s in source_ids for a in metas[s]['source']['artifactIds']]
   batch['procedures'].append(p)
  for f in spec.get('formSnapshots',[]):
   f=f.copy();key=f.pop('procedureKey');sid=f.pop('sourceId');m=metas[sid]
   f.update(authorityId=aid,procedureId=aid+'-'+key,url=m['source']['url'],observedAt=m['source']['retrievedAt'],sourceVersion=m['source']['sourceVersion'],artifactIds=m['source']['artifactIds'],sourceIds=[sid])
   batch['formSnapshots'].append(f)
   next(p for p in batch['procedures'] if p['id']==f['procedureId']).setdefault('formSnapshotIds',[]).append(f['id'])
  for issue in ISSUES:
   procs=[p for p in batch['procedures'] if p['authorityId']==aid and issue in p['issueIds']]
   statuses=[p.get('coverage',{}).get(issue,'unresolved_gap') for p in procs]
   status=('gap' if not procs or all(s=='unresolved_gap' for s in statuses) else ('partial' if all(p['verificationStatus']=='partial' for p in procs) else 'verified'))
   batch['coverage'].append({'authorityId':aid,'issueId':issue,'status':status,'coverageKind':statuses[0] if statuses else 'unresolved_gap','procedureIds':[p['id'] for p in procs],'sourceIds':sorted({s for p in procs for s in p['sourceIds']}) if procs else list(metas),'notes':[g for p in procs for g in p.get('gaps',[])] if procs else ['No verified issue-specific procedure or responsibility handoff established from this batch. Do not infer jurisdiction or dispatch.']})
 if include_population:
  meta=json.loads((CACHE/(REGISTRY_SOURCE+'.json')).read_text())
  batch['sources'].append(meta['source']);batch['artifacts'].append(artifact(meta))
  raw=(CACHE/'statcan-98100004.csv').read_bytes();digest=hashlib.sha256(raw).hexdigest();now=ranking['verifiedAt']
  pop_version='2021-'+hashlib.sha256((ranking['verifiedAt']+'|'+digest).encode()).hexdigest()[:16]
  source={'id':POP_SOURCE,'authorityId':'ontario','url':POP_URL,'title':'Statistics Canada table 98-10-0004-01: 2021 Population and dwelling counts, entire-table CSV','retrievedAt':now,'verifiedAt':now,'extractedText':ranking['method'],'contentHash':hashlib.sha256(ranking['method'].encode()).hexdigest(),'sourceVersion':pop_version,'artifactIds':[POP_SOURCE+'-'+pop_version],'verificationStatus':'verified','gaps':[]}
  popmeta={'source':source,'rawPath':str((CACHE/'statcan-98100004.csv').relative_to(ROOT)),'mimeType':'text/csv'}
  batch['sources'].append(source);batch['artifacts'].append(artifact(popmeta))
 path=ROOT/'data/municipal'/f'{batch_id}.import.json';path.write_text(json.dumps(batch,ensure_ascii=False)+'\n')
 public={k:v for k,v in batch.items() if k not in ('artifacts','sources')}
 public['sources']=[{k:v for k,v in s.items() if k!='extractedText'} for s in batch['sources']]
 (ROOT/'data/municipal'/f'{batch_id}.json').write_text(json.dumps(public,indent=2,ensure_ascii=False)+'\n')
 print(json.dumps({'batchId':batch_id,'path':str(path),'authorities':len(authority_ids),'municipalities':len(batch['municipalities']),'procedures':len(batch['procedures']),'verifiedProcedures':sum(p['verificationStatus']=='verified' for p in batch['procedures']),'sources':len(batch['sources']),'artifacts':len(batch['artifacts']),'coverageCells':len(batch['coverage'])}))
 return path

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch-id',required=True);p.add_argument('--authority',action='append',required=True);p.add_argument('--include-population',action='store_true');a=p.parse_args()
 build(a.authority,a.batch_id,a.include_population)
