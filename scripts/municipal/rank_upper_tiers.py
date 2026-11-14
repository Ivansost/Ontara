"""Rank actual upper-tier governments by summed official 2021 member CSD counts."""
from __future__ import annotations
import csv, hashlib, io, json, re, unicodedata, zipfile
import requests
from datetime import datetime,timezone
from pathlib import Path
from source_tools import ROOT,CACHE,capture

REGISTRY_URL='https://data.ontario.ca/dataset/62e83cbc-0731-4d66-abdc-2f2b31bcd76c/resource/6783a586-6b05-4a73-9663-e60a6963c91e/download/municipalities_-_en_2026-0526.csv'
POP_URL='https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000401'
REGISTRY_SOURCE='ontario-municipal-registry-2026'
POP_SOURCE='statcan-2021-csd-population'

def norm(s):
 return re.sub('[^a-z0-9]','',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower().replace('&','and'))
def slug(s):
 return re.sub('[^a-z0-9]+','-',unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()).strip('-')
def name_from_html(s):
 return re.sub('<[^>]+>','',s).strip()
def parse_name(s):
 name=name_from_html(s)
 return re.sub(r', (?:Township|Municipality|City|Town|Village|County|Regional Municipality|District Municipality|United Counties) of$','',name)
def make_id(name,status,full):
 if status=='Upper Tier':
  if name in ('Peel','York','Durham','Halton','Waterloo','Niagara'): return slug(name)+'-region'
  if name=='Muskoka': return 'muskoka-district'
  if name=='Prescott and Russell': return 'prescott-russell-counties'
  if name=='Leeds and Grenville': return 'leeds-grenville-counties'
  if name=='Stormont, Dundas and Glengarry': return 'stormont-dundas-glengarry-counties'
  return slug(name)+'-county'
 suffix=next((x.lower() for x in ['Township','City','Town','Village','Municipality'] if re.search(r', '+x+r' of$',full)), 'municipality')
 return slug(name)+'-'+suffix

def main():
 registry_meta=capture(REGISTRY_SOURCE,'ontario',REGISTRY_URL,'Ontario Ministry of Municipal Affairs and Housing: municipalities registry, June 2026')
 # StatsCan archive was fetched unchanged from its official entire-table download.
 source_file=CACHE/'statcan-98100004.csv'
 if not source_file.exists():
  response=requests.get('https://www150.statcan.gc.ca/n1/tbl/csv/98100004-eng.zip',timeout=90);response.raise_for_status()
  archive=zipfile.ZipFile(io.BytesIO(response.content))
  source_file.write_bytes(archive.read('98100004.csv'))
 statcan=list(csv.DictReader(source_file.open(encoding='utf-8-sig')))
 csds={(norm(r['GEO']),r['DGUID'][9:13]):r for r in statcan if r['DGUID'].startswith('2021A000535')}
 cd_codes={norm(r['GEO']):r['DGUID'][9:13] for r in statcan if r['DGUID'].startswith('2021A000335')}
 aliases={'thenationmunicipality':'thenationlanation'}
 registry=list(csv.DictReader((ROOT/registry_meta['rawPath']).open(encoding='utf-8-sig')))
 records=[]
 for r in registry:
  full=name_from_html(r['Municipality']);name=parse_name(r['Municipality'])
  name='Stormont, Dundas and Glengarry' if r['Municipal status']=='Upper Tier' and r['Geographic area']=='Stormont, Dundas and Glengarry' else name
  link=re.search(r'href="([^"]+)"',r['Municipality'])
  url=link.group(1) if link else None
  records.append({'name':name,'fullName':full,'type':r['Municipal status'],'area':r['Geographic area'],'officialUrl':url,'id':make_id(name,r['Municipal status'],full)})
 uppers=[r for r in records if r['type']=='Upper Tier'];miss=[]
 popkey=next(k for k in statcan[0] if ': Population, 2021' in k)
 for u in uppers:
  members=[r.copy() for r in records if r['type']=='Lower Tier' and r['area']==u['area']]
  for m in members:
   key=aliases.get(norm(m['name']),norm(m['name']))
   csd=csds.get((key,cd_codes[norm(u['area'])]))
   if csd is None: miss.append(m['name']);continue
   m.update(population2021=int(csd[popkey]),csdName=csd['GEO'],csdDguid=csd['DGUID'])
  u['members']=members
  u['population2021']=sum(m.get('population2021',0) for m in members)
  u['excludedSingleTier']=[r for r in records if r['type']=='Single Tier' and r['area']==u['area']]
 if miss: raise ValueError('Unmatched CSD names: '+repr(miss))
 uppers.sort(key=lambda x:x['population2021'],reverse=True)
 for i,u in enumerate(uppers,1):u['rank']=i
 out={'method':'Sum 2021 Census population counts from Statistics Canada table 98-10-0004-01 for the lower-tier members listed in Ontario municipal registry (validated June 2026). Use only Lower Tier rows; all Single Tier rows are excluded even when their geographic area names match a county. Census-division totals and designated places are never added. 2021 boundaries/counts used consistently; registry membership is current and matched by normalized CSD name, with one explicit bilingual alias for The Nation / La Nation.','populationYear':2021,'registryUrl':REGISTRY_URL,'populationUrl':POP_URL,'populationDownloadUrl':'https://www150.statcan.gc.ca/n1/tbl/csv/98100004-eng.zip','verifiedAt':datetime.now(timezone.utc).isoformat(),'upperTiers':uppers}
 (ROOT/'data/municipal/population_ranking_2021.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
 for u in uppers: print(u['rank'],u['id'],u['population2021'],len(u['members']))

if __name__=='__main__':main()
