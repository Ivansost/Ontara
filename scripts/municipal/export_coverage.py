"""Export the frozen 20x8 research matrix; never turn a handoff into live coverage."""
from __future__ import annotations
import csv,json
from pathlib import Path
from source_tools import ROOT
from build_batches import ISSUES

DATA=ROOT/'data/municipal'
LABELS={'roads-pothole':'Pothole','roads-pavement':'Pavement','roads-debris-loose':'Loose debris','roads-debris-object':'Object','roads-sidewalk':'Sidewalk','roads-curb':'Curb','roads-sign':'Sign','roads-safety':'Safety'}

def main():
 batches=[json.loads(p.read_text()) for p in sorted(DATA.glob('roads-batch-0[1-4]-20261114.json'))]
 ranking=json.loads((DATA/'population_ranking_2021.json').read_text())
 coverage=[row for b in batches for row in b['coverage']]
 sources={s['id']:s for b in batches for s in b['sources']}
 authorities={m['id']:m for b in batches for m in b['municipalities'] if m['type']=='upper-tier'}
 cells={(row['authorityId'],row['issueId']):row for row in coverage}
 assert len(cells)==160 and len(authorities)==20
 assert set(authorities)=={u['id'] for u in ranking['upperTiers'][:20]}
 for row in coverage:
  assert row.get('sourceIds') and row.get('coverageKind')
  assert row.get('procedureIds') or row.get('notes')
  assert all(sid in sources for sid in row['sourceIds'])
 output={'populationYear':2021,'selectionMethod':ranking['method'],'scope':'Roads only. D=detailed published procedure; H=sourced general/responsibility handoff; H?=partial responsibility handoff; G=explicit unresolved gap. All integrations research_only.','authorities':20,'issueIds':ISSUES,'coverage':coverage}
 (DATA/'coverage_matrix.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')
 with (DATA/'coverage_matrix.csv').open('w',newline='') as stream:
  fields=['rank','authorityId','authorityName','population2021','issueId','status','coverageKind','procedureIds','sourceIds','sourceUrls','notes']
  w=csv.DictWriter(stream,fieldnames=fields);w.writeheader()
  for u in ranking['upperTiers'][:20]:
   for issue in ISSUES:
    row=cells[(u['id'],issue)];w.writerow({'rank':u['rank'],'authorityId':u['id'],'authorityName':u['fullName'],'population2021':u['population2021'],**{k:row[k] for k in ['issueId','status','coverageKind']},'procedureIds':';'.join(row['procedureIds']),'sourceIds':';'.join(row['sourceIds']),'sourceUrls':';'.join(sources[s]['url'] for s in row['sourceIds']),'notes':' | '.join(row.get('notes',[]))})
 def mark(row):
  return 'G' if row['coverageKind']=='unresolved_gap' else ('D' if row['coverageKind']=='verified_procedure' else ('H?' if row['status']=='partial' else 'H'))
 lines=['# Ontara Roads: 20 × 8 coverage matrix','','Verified November 14, 2026. All entries are public-source research. **No live municipal integration is enabled by this matrix.**','','D = observed detailed published procedure; H = sourced general contact or responsibility handoff; H? = partial responsibility evidence; G = explicit unresolved gap. A handoff can be useful while asset ownership, exact intake requirements or acceptance remain unverified.','','| Rank | Upper tier | 2021 member population | '+' | '.join(LABELS[i] for i in ISSUES)+' |','| '+' | '.join(['---','---','---']+['---']*8)+' |']
 for u in ranking['upperTiers'][:20]:
  first_source=next(s for b in batches for p in b['procedures'] if p['authorityId']==u['id'] for s in p['sourceIds'])
  lines.append('| '+str(u['rank'])+' | ['+u['fullName']+']('+sources[first_source]['url']+') | '+f"{u['population2021']:,}"+' | '+' | '.join(mark(cells[(u['id'],i)]) for i in ISSUES)+' |')
 lines += ['','The 160 cells comprise **3 D, 111 H, 1 H?, and 45 G**. Source verification does not prove asset ownership, acceptance, receipt, repair or an automated integration. See [machine-readable cells and notes](coverage_matrix.json) and [CSV with source URLs](coverage_matrix.csv).','','Population ranking sums the 2021 Census counts of actual lower-tier members in Ontario’s current official registry. Separated single-tier cities and all nonmember census subdivisions are excluded; census-division totals are not substituted. Hamilton township is joined within Northumberland, avoiding confusion with the single-tier City of Hamilton. Halton was imported first for the demo despite rank 4. [Ontario registry](https://data.ontario.ca/en/dataset/municipalities), [Statistics Canada table 98-10-0004-01](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000401).','','Specific limitations include generally unverified sidewalk ownership; asset-specific curb responsibility; Renfrew’s linked form returning HTTP403; JavaScript-only portal questionnaires; and unverified urgency/tracking/repair targets where not published. Requirements and observed field labels are stored only when actually visible or explicitly stated. No resident data, report submission, phone call or live email was used for this research.']
 (DATA/'coverage_matrix.md').write_text('\n'.join(lines)+'\n')
 print(json.dumps({'authorities':20,'coverageCells':160,'detailed':3,'handoffs':111,'partialHandoffs':1,'gaps':45}))
if __name__=='__main__':main()
