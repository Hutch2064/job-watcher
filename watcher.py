"""Collect public ATS JSON, then deterministically rebuild posting history."""
import argparse
import csv
import gzip
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = json.loads((ROOT / 'sources.json').read_text())
FIELDS = 'posting_id source source_id employer title location department posted_date url in_role first_run first_seen last_seen status removed_date'.split()
ROLE = re.compile(r'\b(portfolio|asset allocation|investment|investing|equity research|fixed.income|credit research|quantitative research|quantitative analyst|fund research|manager research|etf|wealth (?:management|advisor)|financial planning|investment consulting|ocio|multi.asset|systematic|risk analytics|research analyst)\b', re.I)
EXCLUDE = re.compile(r'\b(sales|marketing|accounting|accountant|reconciliation|administrative assistant|recruiter|tax|auditor|software engineer|cybersecurity|compliance|legal counsel)\b', re.I)

def in_role(title):
    return bool(ROLE.search(title) and not EXCLUDE.search(title))

def request(url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={'User-Agent':'JobWatcher academic project/1.0', 'Accept':'application/json', 'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=35) as response:
        return json.load(response)

def fetch(source):
    kind, board = source['type'], source['board']
    if kind == 'greenhouse':
        data = request(f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true')
        if not isinstance(data.get('jobs'), list): raise ValueError('Missing jobs list')
        if len(data['jobs']) > 5000: raise ValueError('Board exceeds 5,000; configure a supported search')
        return data
    if kind == 'lever':
        data = request(f'https://api.lever.co/v0/postings/{board}?mode=json')
        if not isinstance(data, list): raise ValueError('Missing postings list')
        if len(data) > 5000: raise ValueError('Board exceeds 5,000; configure a supported search')
        return data
    base = f"https://{source['host']}.myworkdayjobs.com/wday/cxs/{source['host'].split('.')[0]}/{board}/jobs"
    pages, offset, total = [], 0, None
    while total is None or offset < total:
        page = request(base, {'appliedFacets':{}, 'limit':20, 'offset':offset, 'searchText':source.get('search','')})
        if not isinstance(page.get('jobPostings'), list) or not isinstance(page.get('total'), int): raise ValueError('Invalid Workday response')
        if total is None: total = page['total']
        if total > 5000 and not source.get('search'): raise ValueError('Board exceeds 5,000; configure a search')
        if (page['total'] not in (0, total)) or (offset < total and not page['jobPostings']): raise ValueError('Incomplete or changing pagination')
        pages.append(page); offset += len(page['jobPostings'])
        if total == 0: break
    return {'pages':pages}

def normalize(source, data):
    kind = source['type']; rows = []
    if kind == 'greenhouse': items = data['jobs']
    elif kind == 'lever': items = data
    else: items = [j for page in data['pages'] for j in page['jobPostings']]
    for j in items:
        if kind == 'greenhouse':
            sid = str(j['id']); loc = (j.get('location') or {}).get('name',''); dep = ', '.join(d.get('name','') for d in j.get('departments',[])); url = j['absolute_url']; posted = (j.get('first_published') or '')[:10]
        elif kind == 'lever':
            sid = str(j['id']); cat = j.get('categories') or {}; loc = cat.get('location',''); dep = cat.get('department') or cat.get('team') or ''; url = j['hostedUrl']; posted = datetime.fromtimestamp(j['createdAt']/1000, timezone.utc).date().isoformat() if j.get('createdAt') else ''
        else:
            path = j['externalPath']; sid = path.rsplit('_',1)[-1]; loc = j.get('locationsText',''); dep = ''; posted = ''; url = f"https://{source['host']}.myworkdayjobs.com/en-US/{source['board']}{path}"
        title = j['text'] if kind == 'lever' else j['title']
        rows.append(dict(posting_id=source['id']+':'+sid, source=source['id'], source_id=sid, employer=source['name'], title=title, location=loc or '', department=dep or '', posted_date=posted, url=url, in_role=str(in_role(title)).lower()))
    if len({r['posting_id'] for r in rows}) != len(rows): raise ValueError('Duplicate source IDs')
    return rows

def build():
    history = {}; seen_sources = set(); dates = set(); by_id = {s['id']:s for s in SOURCES}
    for folder in sorted((ROOT/'data/raw').glob('????-??-??')):
        for path in sorted(folder.glob('*.json.gz')):
            source = by_id.get(path.name[:-8])
            if not source: raise ValueError(f'Unknown source: {path}')
            with gzip.open(path, 'rt', encoding='utf-8') as f: rows = normalize(source, json.load(f))
            date = folder.name; dates.add(date); first = source['id'] not in seen_sources; seen_sources.add(source['id']); ids = set()
            for row in rows:
                key = row['posting_id']; ids.add(key)
                if key not in history:
                    history[key] = {**row, 'first_run':str(first).lower(), 'first_seen':date, 'last_seen':date, 'status':'open', 'removed_date':''}
                else:
                    history[key].update(row); history[key].update(last_seen=date, status='open', removed_date='')
            for key, row in history.items():
                if row['source'] == source['id'] and key not in ids and row['status'] == 'open': row.update(status='removed', removed_date=date)
    target = ROOT/'data/history.csv'; target.parent.mkdir(exist_ok=True)
    with target.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator='\n'); writer.writeheader(); writer.writerows(history[k] for k in sorted(history))
    return history, dates

def collect():
    now = datetime.now(timezone.utc); date = now.date().isoformat(); folder = ROOT/'data/raw'/date; folder.mkdir(parents=True, exist_ok=True); results=[]
    for s in SOURCES:
        path = folder/(s['id']+'.json.gz')
        try:
            data = fetch(s); rows = normalize(s, data)
            # Write a complete file atomically; a failed rerun cannot masquerade as today's successful source.
            temp = path.with_suffix('.tmp')
            with temp.open('wb') as raw:
                with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as out: out.write(json.dumps(data, ensure_ascii=False, separators=(',',':')).encode())
            temp.replace(path); results.append({'name':s['name'], 'ok':True, 'count':len(rows)}); print(s['name'],len(rows), flush=True)
        except Exception as exc:
            path.unlink(missing_ok=True); results.append({'name':s['name'], 'ok':False, 'count':0, 'error':str(exc)}); print(s['name'], 'FAILED', exc, file=sys.stderr, flush=True)
    history, dates = build(); rows = list(history.values())
    status = {'run_time':now.isoformat().replace('+00:00','Z'), 'first_run_date':min(dates) if dates else '', 'days_with_success':len(dates), 'open':sum(r['status']=='open' for r in rows), 'new_today':sum(r['first_seen']==date and r['first_run']=='false' for r in rows), 'removed_today':sum(r['removed_date']==date for r in rows), 'sources':results}
    (ROOT/'data/status.json').write_text(json.dumps(status, indent=2)+'\n')
    if not dates: raise RuntimeError('No source produced a raw file')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command', choices=['collect','build']); args=parser.parse_args()
    collect() if args.command=='collect' else build()
