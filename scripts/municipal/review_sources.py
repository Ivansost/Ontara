"""Read-only captures and review excerpts; no form submission or browser interaction."""
from pathlib import Path
import concurrent.futures,json,re,sys
from source_tools import capture,PageText,ROOT,CACHE

def review(args):
 try:
  m=capture(*args)
  if m['mimeType'] not in ('text/html','application/xhtml+xml'):
   return {'id':args[0],'mimeType':m['mimeType'],'byteCount':m['byteCount'],'note':'Binary/data source captured; no HTML parsing or visual map verification claimed.'}
  raw=(ROOT/m['rawPath']).read_text(errors='replace');main=re.search(r'<main\b[^>]*>([\s\S]*?)</main>',raw,re.I)
  p=PageText();p.feed(main.group(1) if main else raw);t=p.text();(CACHE/(args[0]+'.review.txt')).write_text(t)
  lines=[line for line in t.splitlines() if re.search(r'report|contact|call |telephone|pothole|sidewalk|county road|provincial|private road|local road|sign |urgent|@|hours|after-hours',line,re.I)]
  return {'id':args[0],'url':args[2],'excerpt':'\n'.join(lines)[:7000],'links':sorted(set(u for u in m['links'] if re.search(r'forms?\.|mailto:|report.?a|report.*road|road.*(faq|map)|public.?works|contact|service.*request',u,re.I)))[:15]}
 except Exception as exc:return {'id':args[0],'errorType':type(exc).__name__,'error':str(exc)[:220]}
if __name__=='__main__':
 items=json.loads(Path(sys.argv[1]).read_text())
 for r in concurrent.futures.ThreadPoolExecutor(max_workers=8).map(review,items):print(json.dumps(r,ensure_ascii=False))
