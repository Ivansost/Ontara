"""Official Ontario WGS84 boundary enrichment through the backend ResearchBatch contract.
Uses existing research-tool requests/Shapely; no runtime resolver or geospatial index.
"""
from __future__ import annotations
import csv,hashlib,json,re
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests
from shapely.geometry import shape,mapping
from shapely.ops import unary_union
from source_tools import ROOT,CACHE,capture,artifact
from rank_upper_tiers import norm,parse_name,name_from_html,make_id,REGISTRY_SOURCE,POP_SOURCE,REGISTRY_URL

BASE='https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/'
BATCH='roads-boundaries-20261114'
TOLERANCE=0.0001  # Output WGS84 degrees (~11m latitude); manual-confirmation geography only.

def url(path,params):return requests.Request('GET',path,params=params).prepare().url

def source_data(sid,authority,url_value,title):
 m=capture(sid,authority,url_value,title)
 if m['httpStatus']!=200:raise ValueError('Unavailable official boundary source')
 return m

def main():
 ranking=json.loads((ROOT/'data/municipal/population_ranking_2021.json').read_text());selected=ranking['upperTiers'][:20]
 bases=[json.loads(p.read_text()) for p in sorted((ROOT/'data/municipal').glob('roads-batch-0[1-4]-20261114.json'))]
 munis={m['id']:m for b in bases for m in b['municipalities']}
 registry_meta=capture(REGISTRY_SOURCE,'ontario',REGISTRY_URL,'Ontario official municipality registry')
 registry=list(csv.DictReader((ROOT/registry_meta['rawPath']).open(encoding='utf-8-sig')))
 csds=list(csv.DictReader((CACHE/'statcan-98100004.csv').open(encoding='utf-8-sig')))
 popkey=next(k for k in csds[0] if ': Population, 2021' in k)
 cds={norm(x['GEO']):x['DGUID'][9:13] for x in csds if x['DGUID'].startswith('2021A000335')}
 popmap={(norm(x['GEO']),x['DGUID'][9:13]):int(x[popkey]) for x in csds if x['DGUID'].startswith('2021A000535') and x[popkey].isdigit()}
 single_names={norm(x['name']) for u in selected for x in u['excludedSingleTier']}|{'toronto','hamilton'}
 singles=[]
 for r in registry:
  name=parse_name(r['Municipality']);full=name_from_html(r['Municipality'])
  if r['Municipal status']=='Single Tier' and norm(name) in single_names:
   website=re.search(r'href="([^"]+)"',r['Municipality']).group(1)
   m={'id':make_id(name,r['Municipal status'],full),'name':full,'type':'single-tier','parentId':None,'memberIds':[],'officialUrl':website,'population':popmap[(norm(name),cds[norm(r['Geographic area'])])],'populationYear':2021,'populationSourceIds':[REGISTRY_SOURCE,POP_SOURCE,REGISTRY_URL],'sourceIds':[REGISTRY_SOURCE],'sourceVersion':'2021-csd-v1'}
   singles.append((m,name));munis[m['id']]=m
 attrs_path=CACHE/'lio-13-attributes.json'
 if not attrs_path.exists():
  response=requests.get(BASE+'13/query',params={'f':'json','where':'1=1','outFields':'MUNICIPAL_NAME,MUNICIPAL_NAME_SHORTFORM,MUNICIPAL_TYPE','returnGeometry':'false'},timeout=35);response.raise_for_status();attrs_path.write_text(response.text)
 upper_attrs=json.loads(attrs_path.read_text())['features']
 upper_names={norm(u['area']):u for u in selected}
 selected_fullnames=sorted({x['attributes']['MUNICIPAL_NAME'] for x in upper_attrs if norm(x['attributes']['MUNICIPAL_NAME_SHORTFORM']) in upper_names and x['attributes']['MUNICIPAL_TYPE']=='Upper Tier Municipality'})
 assert len(selected_fullnames)==20
 quoted=lambda x:"'"+x.replace("'","''")+"'"
 upper_where="MUNICIPAL_TYPE='Upper Tier Municipality' AND MUNICIPAL_NAME IN ("+','.join(map(quoted,selected_fullnames))+")"
 single_shortnames=[name.upper() for _,name in singles]
 lower_where="UPPER_TIER_MUNICIPALITY IN ("+','.join(map(quoted,selected_fullnames))+") OR (MUNICIPAL_TYPE='Single Tier Municipality' AND MUNICIPAL_NAME_SHORTFORM IN ("+','.join(map(quoted,single_shortnames))+"))"
 params={'f':'geojson','outFields':'*','returnGeometry':'true','outSR':'4326','returnZ':'false','returnM':'false','maxAllowableOffset':str(TOLERANCE),'geometryPrecision':'6'}
 metadata=[]
 metadata.append(source_data('ontario-boundary-catalogue','ontario','https://data.ontario.ca/api/3/action/package_show?id=municipal-boundaries','Ontario municipal boundary catalogue metadata'))
 for layer in [13,14]:metadata.append(source_data('lio-boundary-layer-'+str(layer),'ontario',BASE+str(layer)+'?f=pjson','Land Information Ontario official municipal boundary layer '+str(layer)))
 upper=source_data('lio-selected-upper-boundaries','ontario',url(BASE+'13/query',{**params,'where':upper_where}),'Ontario official selected upper-tier boundaries: WGS84, generalized 0.0001 degree')
 lower=source_data('lio-selected-lower-single-boundaries','ontario',url(BASE+'14/query',{**params,'where':lower_where}),'Ontario official selected lower/single-tier boundaries: WGS84, generalized 0.0001 degree')
 metadata.extend([upper,lower])
 geometry_by_id=defaultdict(list);properties_by_id=defaultdict(list);unmatched=[];repairs=[]
 member_lookup={}
 for u in selected:
  for m in u['members']:
   alias='thenation' if norm(m['name'])=='thenationmunicipality' else norm(m['name'])
   member_lookup[(alias,norm(u['area']))]=m['id']
 single_lookup={norm(name):m['id'] for m,name in singles}
 def upper_key(value):
  return next((norm(u['area']) for u in selected if value and norm(u['area']) in norm(value)),None)
 for meta,is_upper in [(upper,True),(lower,False)]:
  raw=json.loads((ROOT/meta['rawPath']).read_text())
  if raw.get('type')!='FeatureCollection' or raw.get('error'):raise ValueError('Not GeoJSON FeatureCollection')
  if raw.get('exceededTransferLimit'):raise ValueError('Official boundary response truncated')
  for feature in raw['features']:
   props=feature['properties'];key=norm(props['MUNICIPAL_NAME_SHORTFORM'])
   if is_upper:mid=upper_names.get(key,{}).get('id')
   elif props['MUNICIPAL_TYPE']=='Single Tier Municipality':mid=single_lookup.get(key)
   else:mid=member_lookup.get((key,upper_key(props.get('UPPER_TIER_MUNICIPALITY'))))
   if not mid:unmatched.append(props);continue
   geom=shape(feature['geometry'])
   if not geom.is_valid:
    geom=geom.buffer(0);repairs.append({'municipalityId':mid,'objectId':props['OBJECTID'],'method':'Shapely buffer(0) to repair generalized source polygon'})
   if geom.is_empty or geom.geom_type not in ('Polygon','MultiPolygon') or not geom.is_valid:raise ValueError('Invalid boundary geometry for '+mid)
   geometry_by_id[mid].append(geom);properties_by_id[mid].append(props)
  # Keep compact searchable metadata text; complete obtained GeoJSON bytes remain in GridFS.
  meta['source']['extractedText']=json.dumps({'source':'Land Information Ontario','outSR':4326,'coordinateOrder':'longitude,latitude','maxAllowableOffsetDegrees':TOLERANCE,'purpose':'Candidate municipality geography only; not road ownership or runtime resolver proof.','features':[f['properties'] for f in raw['features']]},ensure_ascii=False)
  meta['source']['contentHash']=hashlib.sha256(meta['source']['extractedText'].encode()).hexdigest()
  (CACHE/(meta['source']['id']+'.json')).write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
 gaps=[];byname={}
 for mid,m in munis.items():
  geometries=geometry_by_id.get(mid)
  if not geometries:gaps.append('No matched official boundary: '+mid);continue
  geometry=unary_union(geometries)
  if not geometry.is_valid:geometry=geometry.buffer(0)
  if geometry.geom_type not in ('Polygon','MultiPolygon') or not geometry.is_valid:raise ValueError('Invalid merged geometry for '+mid)
  bbox=list(geometry.bounds)
  if not (-180<=bbox[0]<=bbox[2]<=180 and -90<=bbox[1]<=bbox[3]<=90):raise ValueError('Invalid WGS84 bounds')
  data=dict(mapping(geometry));data['bbox']=bbox
  if len(json.dumps(data).encode())>12*1024*1024:raise ValueError('Municipality geometry too large')
  sid=upper['source']['id'] if m['type']=='upper-tier' else lower['source']['id']
  m['boundary']=data;m['sourceIds']=sorted(set(m.get('sourceIds',[])+[sid]));m['sourceVersion']='lio-wgs84-'+hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:16]
  byname[mid]={'type':m['type'],'parts':len(geometries),'bbox':bbox,'geometryType':geometry.geom_type,'coordinateBytes':len(json.dumps(data).encode()),'sourceObjectIds':[p['OBJECTID'] for p in properties_by_id[mid]]}
 # Preserve actual obtained official road map PDF as a separate public artifact.
 pdf_path=CACHE/'middlesex-road-map.json'
 if pdf_path.exists():
  pdf=json.loads(pdf_path.read_text());pdf['source']['title']='Middlesex County 2021 Road Map (official linked PDF)';metadata.append(pdf)
 batch={'schemaVersion':'1.0','batchId':BATCH,'municipalities':[m for m in munis.values() if m.get('boundary')],'sources':[m['source'] for m in metadata],'procedures':[],'formSnapshots':[],'artifacts':[artifact(m) for m in metadata],'coverage':[],'gaps':gaps+['Generalized official WGS84 geometry supports candidate geography only. Manual incident confirmation and separate asset-owner validation remain required. No runtime resolver or municipal submission integration is claimed.']}
 (ROOT/'data/municipal'/f'{BATCH}.import.json').write_text(json.dumps(batch,ensure_ascii=False)+'\n')
 public={k:v for k,v in batch.items() if k not in ('sources','artifacts')};public['sources']=[{k:v for k,v in s.items() if k!='extractedText'} for s in batch['sources']]
 (ROOT/'data/municipal'/f'{BATCH}.json').write_text(json.dumps(public,ensure_ascii=False)+'\n')
 summary={'createdAt':datetime.now(timezone.utc).isoformat(),'outSR':4326,'maxAllowableOffsetDegrees':TOLERANCE,'sourceLicense':'Open Government Licence Ontario','upperTiers':sum(m['type']=='upper-tier' for m in batch['municipalities']),'lowerTiers':sum(m['type']=='lower-tier' for m in batch['municipalities']),'singleTiers':sum(m['type']=='single-tier' for m in batch['municipalities']),'gaps':gaps,'unmatchedSourceParts':unmatched,'repairs':repairs,'records':byname,'sources':[s['id'] for s in batch['sources']]}
 (ROOT/'data/municipal/boundary_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items() if k not in ('records','unmatchedSourceParts','repairs')}))
if __name__=='__main__':
 try:main()
 except Exception as exc:
  print(json.dumps({'status':'failed','errorType':type(exc).__name__,'reason':str(exc)[:300]}));raise SystemExit(1)
