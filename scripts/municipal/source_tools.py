"""Official-source capture for bounded municipal Roads research. No submissions."""
from __future__ import annotations
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
import requests

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / 'data/municipal/source_cache'

class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
        self.links = []
        self.fields = []
        self.title = ''
        self.in_title = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script','style','noscript','svg'):
            self.skip += 1
        if tag == 'title': self.in_title = True
        if tag in ('p','div','li','section','h1','h2','h3','h4','tr','br'): self.parts.append('\n')
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
        if tag in ('input','select','textarea'):
            self.fields.append({k:v for k,v in a.items() if k in ('id','name','type','required','placeholder','aria-label')})
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript','svg') and self.skip: self.skip -= 1
        if tag == 'title': self.in_title = False
    def handle_data(self, data):
        if not self.skip:
            value = re.sub(r'\s+', ' ', data).strip()
            if value:
                self.parts.append(value + ' ')
                if self.in_title: self.title += value
    def text(self):
        return '\n'.join(re.sub(r'\s+', ' ', s).strip() for s in ''.join(self.parts).split('\n') if s.strip())

def capture(source_id, authority_id, url, title=None, refresh=False, allow_error=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    meta_path = CACHE / f'{source_id}.json'
    if meta_path.exists() and not refresh:
        previous=json.loads(meta_path.read_text())
        # Metadata and obtained JSON bytes must never share a filename.
        if previous.get('rawPath') is None or (ROOT/previous['rawPath']).resolve()!=meta_path.resolve():
            return previous
    now = datetime.now(timezone.utc).isoformat()
    response = requests.get(url, timeout=40, headers={'User-Agent':'OntaraHackathonResearch/1.0 (public-source verification; no form submission)'})
    if response.status_code >= 400:
        if not allow_error:
            response.raise_for_status()
        version = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+hashlib.sha256((url+'|HTTP'+str(response.status_code)).encode()).hexdigest()[:16]
        source = {'id':source_id,'authorityId':authority_id,'url':url,'title':title or source_id,
                  'retrievedAt':now,'verifiedAt':None,'extractedText':'','contentHash':hashlib.sha256(b'').hexdigest(),
                  'sourceVersion':version,'artifactIds':[],'gaps':['HTTP '+str(response.status_code)+'; source/form content was not obtainable. No successful snapshot is claimed.'],
                  'verificationStatus':'unavailable'}
        meta = {'source':source,'finalUrl':response.url,'httpStatus':response.status_code,'rawPath':None,'mimeType':None,'byteCount':0,'links':[],'observedFields':[]}
        meta_path.write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
        return meta
    response.raise_for_status()
    raw = response.content
    digest = hashlib.sha256(raw).hexdigest()
    if refresh and meta_path.exists():
        previous=json.loads(meta_path.read_text())
        if previous.get('rawSha256')==digest and previous.get('rawPath') and (ROOT/previous['rawPath']).resolve()!=meta_path.resolve():
            return previous
    version=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+digest[:16]
    mime = response.headers.get('Content-Type', 'application/octet-stream').split(';')[0]
    extension = 'pdf' if mime == 'application/pdf' else ('csv' if 'csv' in mime else ('json' if 'json' in mime else 'html'))
    raw_path = CACHE / f'{source_id}.body.{extension}'
    raw_path.write_bytes(raw)
    parsed = PageText()
    text = ''
    if extension == 'html':
        parsed.feed(response.text)
        text = parsed.text()
    elif extension in ('csv','json'):
        text = response.text
    source = {
        'id':source_id,'authorityId':authority_id,'url':url,'title':title or parsed.title or source_id,
        'retrievedAt':now,'verifiedAt':now,'extractedText':text,'contentHash':hashlib.sha256(text.encode()).hexdigest(),
        'sourceVersion':version,'artifactIds':[f'{source_id}-{version}'],
        'gaps':[],'verificationStatus':'verified',
    }
    meta = {'source':source,'finalUrl':response.url,'httpStatus':response.status_code,
            'rawPath':str(raw_path.relative_to(ROOT)), 'mimeType':mime,'byteCount':len(raw),'rawSha256':digest,
            'links':[urljoin(response.url,u) for u in parsed.links], 'observedFields':parsed.fields}
    meta_path.write_text(json.dumps(meta,indent=2,ensure_ascii=False)+'\n')
    (CACHE / f'{source_id}.txt').write_text(text)
    return meta

_FROZEN_ARTIFACTS = None

def artifact(meta):
    global _FROZEN_ARTIFACTS
    if _FROZEN_ARTIFACTS is None:
        _FROZEN_ARTIFACTS = {}
        for result_path in sorted((ROOT/'data/municipal').glob('*.result.json')):
            try:
                run=json.loads(result_path.read_text())
                payload_path=result_path.with_name(result_path.name.replace('.result.json','.import.json'))
                if run.get('status')=='completed' and payload_path.exists():
                    for item in json.loads(payload_path.read_text()).get('artifacts',[]):
                        _FROZEN_ARTIFACTS.setdefault(item['id'],item)
            except (ValueError,OSError):
                pass
    known=_FROZEN_ARTIFACTS.get(meta['source']['artifactIds'][0]) if meta['source']['artifactIds'] else None
    if known is not None:
        return known
    s = meta['source']; raw = (ROOT / meta['rawPath']).read_bytes()
    if meta.get('rawSha256') and hashlib.sha256(raw).hexdigest()!=meta['rawSha256']:
        raise ValueError('Obtained source bytes do not match capture fingerprint: '+s['id'])
    # Public snapshots retain page/field evidence while removing ephemeral tokens.
    if meta['mimeType'] in ('text/html','application/xhtml+xml'):
        html = raw.decode('utf-8', errors='replace')
        def clean_input(match):
            tag = match.group(0)
            if re.search(r'(?:type=[\"\']hidden|csrf|token|password|session)', tag, re.I):
                tag = re.sub(r'\svalue=(?:\"[^\"]*\"|\'[^\']*\')', ' value=\"[REDACTED]\"', tag, flags=re.I)
            return tag
        html = re.sub(r'<input\b[^>]*>', clean_input, html, flags=re.I)
        html = re.sub(r'\snonce=(?:\"[^\"]*\"|\'[^\']*\')', ' nonce=\"[REDACTED]\"', html, flags=re.I)
        raw = html.encode('utf-8')
    return {'id':s['artifactIds'][0],'filename':Path(meta['rawPath']).name,
            'mimeType':meta['mimeType'],'contentBase64':base64.b64encode(raw).decode(),
            'visibility':'public','sourceId':s['id'],'sourceVersion':s['sourceVersion'],
            'authorityId':s['authorityId'],'expectedSha256':hashlib.sha256(raw).hexdigest()}

if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('id');p.add_argument('authority');p.add_argument('url');a=p.parse_args()
    m=capture(a.id,a.authority,a.url)
    print(json.dumps({k:v for k,v in m.items() if k not in ('source','links')},indent=2))
    print(m['source']['extractedText'][:24000])
