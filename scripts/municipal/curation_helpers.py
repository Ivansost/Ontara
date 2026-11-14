"""Utilities for the hand-verified public Roads curation file, not runtime routing."""
import json
from source_tools import ROOT

DATA=ROOT/'data/municipal/roads_authorities.json'

def procedure(key,title,issues,text,rules,steps,*,sources,phone=None,email=None,form=None,facts=None,follow_up=None,gaps=None,coverage=None,status='verified'):
 p={'key':key,'title':title,'issueIds':issues,'sourceIds':sources,'retrievalText':text,'responsibilityRules':rules,'steps':steps,'requiredFacts':facts or [],'followUpInstructions':follow_up or [],'coverage':coverage or {i:'sourced_handoff' for i in issues},'gaps':gaps or ['The observed source does not specify mandatory incident-report fields, receipt/tracking behavior or a fixed repair deadline.'],'verificationStatus':status,'researchStatus':status,'constraints':['Research only. Source links and contacts are not allowlisted demo execution destinations. No live municipality was contacted or form submitted.']}
 if phone:p['contactPhone']=phone
 if email:p['contactEmail']=email
 if form:p['officialFormUrl']=form
 return p

def save_authority(aid,sources,procedures,snapshots=None):
 records=json.loads(DATA.read_text());r={'authorityId':aid,'sources':[{'id':sid,'url':url} for sid,url in sources],'procedures':procedures}
 if snapshots:r['formSnapshots']=snapshots
 existing=next((i for i,v in enumerate(records) if v['authorityId']==aid),None)
 if existing is None:records.append(r)
 else:records[existing]=r
 DATA.write_text(json.dumps(records,indent=2,ensure_ascii=False)+'\n')
