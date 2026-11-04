"""Collect public ATS JSON, then deterministically rebuild posting history."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
import gzip
from html import unescape
from html.parser import HTMLParser
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = json.loads((ROOT / 'sources.json').read_text())
FIELDS = 'posting_id source source_id employer title location department posted_date url in_role first_run first_seen last_seen status removed_date experience experience_reason'.split()
ROLE = re.compile(r'\b(portfolio|asset allocation|investment|investing|equity research|fixed.income|credit research|credit analyst|equity analyst|quantitative research|quantitative analyst|fund research|manager research|etf|wealth (?:management|advisor)|financial planning|investment consulting|ocio|multi.asset|systematic|risk analytics|research analyst)\b', re.I)
EXCLUDE = re.compile(r'\b(sales|marketing|accounting|accountant|reconciliation|administrative assistant|recruiter|tax|auditor|software engineer|cybersecurity|compliance|legal counsel)\b', re.I)

# Accept joined titles such as InvestmentIntern without matching Internal or International.
INTERNSHIP = re.compile(r'intern(?!al|ation|et)(?:ship|s)?', re.I)
PROGRAM = re.compile(r'program(?!m(?:ing|er)|matic)', re.I)
SUMMER = re.compile(r'summer', re.I)

def in_role(title):
    normalized = INTERNSHIP.sub(lambda m: ' ' + m.group() + ' ', title)
    return bool(ROLE.search(normalized) and not EXCLUDE.search(normalized))

class DescriptionText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'li', 'br', 'div', 'h1', 'h2', 'h3', 'h4'): self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('p', 'li', 'div', 'h1', 'h2', 'h3', 'h4'): self.parts.append('\n')
    def handle_data(self, data): self.parts.append(data)

def plain_text(value):
    parser = DescriptionText(); parser.feed(unescape(value or '')); return unescape(''.join(parser.parts))

SENIOR = re.compile(r'\b(senior|sr\.?|staff|lead|principal|director|vice president|avp|vp|svp|evp|head of|chief|partner|managing director)\b', re.I)
YEARS = re.compile(r'\b(?P<min>\d{1,2}|zero|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:(?:-|–|—|to)\s*(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten))?\s*(?:\+|or more)?[\s-]*(?:years?|yrs?)\b', re.I)
NUMBERS = {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}

def experience_level(title, description=''):
    if INTERNSHIP.search(title): return ('early', 'Internship in title')
    if SENIOR.search(title): return ('experienced', 'Senior-level title')
    observations = []
    for line in plain_text(description).splitlines():
        line = re.sub(r'\b(experience)\.\s+(?=\d)', r'\1: ', line, flags=re.I)
        for sentence in re.split(r'(?<=[.!?])\s+', line):
            for match in YEARS.finditer(sentence):
                context = sentence[max(0, match.start()-90):match.end()+110]
                if not re.search(r'\b(experience|experienced|work history)\b', context, re.I): continue
                # Preferred credentials are useful context but are not minimum requirements.
                preference_context = sentence[max(0, match.start()-35):match.end()+45]
                if re.search(r'\b(preferred|a plus|nice to have|desired|desirable)\b', preference_context, re.I) and not re.search(r'\b(required|minimum|at least|must have)\b', preference_context, re.I): continue
                token = match.group('min').lower()
                minimum = int(token) if token.isdigit() else NUMBERS[token]
                if minimum > 40: continue
                observations.append((minimum, ' '.join(match.group(0).split())))
    if observations:
        minimum, phrase = max(observations, key=lambda x:x[0])
        if minimum >= 3: return ('experienced', f'{phrase} of experience mentioned')
        return ('early', f'{phrase} of experience mentioned')
    if SUMMER.search(title): return ('early', 'Summer in title')
    if PROGRAM.search(title): return ('early', 'Program in title')
    return ('unknown', 'Experience not determined')

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
    # Some Workday listings omit a title. Recover it from the public JSON detail,
    # retaining the original page unchanged; fail the board if recovery is impossible.
    recovered_titles = {}
    for page in pages:
        for job in page['jobPostings']:
            if not job.get('externalPath'):
                raise ValueError('Workday posting has no external path')
            if not job.get('title'):
                path = job['externalPath']
                detail_url = f"https://{source['host']}.myworkdayjobs.com/wday/cxs/{source['host'].split('.')[0]}/{board}{path}"
                info = request(detail_url).get('jobPostingInfo', {})
                title = info.get('title')
                if not title: raise ValueError(f'Workday posting has no recoverable title: {path}')
                recovered_titles[path] = title
    # Detail lookups enrich relevant roles without jeopardizing the complete board snapshot.
    postings = [j for page in pages for j in page['jobPostings'] if in_role(j.get('title') or recovered_titles[j['externalPath']]) and not SENIOR.search(j.get('title') or recovered_titles[j['externalPath']])]
    def detail(job):
        try:
            url = f"https://{source['host']}.myworkdayjobs.com/wday/cxs/{source['host'].split('.')[0]}/{board}{job['externalPath']}"
            info = request(url).get('jobPostingInfo', {})
            return job['externalPath'], info.get('jobDescription', '')
        except Exception:
            return job['externalPath'], ''
    with ThreadPoolExecutor(max_workers=4) as pool:
        details = dict(pool.map(detail, postings))
    return {'pages':pages, 'details':details, 'recovered_titles':recovered_titles}

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
        title = j['text'] if kind == 'lever' else (j.get('title') or data.get('recovered_titles', {}).get(j.get('externalPath', '')) if kind == 'workday' else j['title'])
        if not title: raise ValueError('Posting title unavailable')
        if kind == 'greenhouse': description = j.get('content', '')
        elif kind == 'lever':
            description = ' '.join([j.get('descriptionPlain') or j.get('description') or '', j.get('additionalPlain') or j.get('additional') or ''] + [x.get('text', '') + ' ' + (x.get('content') or '') for x in j.get('lists', [])])
        else: description = data.get('details', {}).get(j['externalPath'], '')
        level, reason = experience_level(title, description)
        rows.append(dict(experience=level, experience_reason=reason, posting_id=source['id']+':'+sid, source=source['id'], source_id=sid, employer=source['name'], title=title, location=loc or '', department=dep or '', posted_date=posted, url=url, in_role=str(in_role(title)).lower()))
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

def fetch_validated(source, attempts=3):
    for attempt in range(attempts):
        try:
            data = fetch(source)
            return data, normalize(source, data)
        except Exception:
            if attempt == attempts - 1: raise
            time.sleep(attempt + 1)

def collect():
    now = datetime.now(timezone.utc); date = now.date().isoformat(); folder = ROOT/'data/raw'/date; folder.mkdir(parents=True, exist_ok=True); results=[]
    def collect_one(s):
        path = folder/(s['id']+'.json.gz')
        try:
            data, rows = fetch_validated(s)
            # Write a complete file atomically; a failed rerun cannot masquerade as today's successful source.
            temp = path.with_suffix('.tmp')
            with temp.open('wb') as raw:
                with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as out: out.write(json.dumps(data, ensure_ascii=False, separators=(',',':')).encode())
            temp.replace(path); print(s['name'],len(rows), flush=True); return {'name':s['name'], 'ok':True, 'count':len(rows)}
        except Exception as exc:
            path.unlink(missing_ok=True); print(s['name'], 'FAILED', exc, file=sys.stderr, flush=True); return {'name':s['name'], 'ok':False, 'count':0, 'error':str(exc)}
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(collect_one, SOURCES))
    history, dates = build(); rows = list(history.values())
    status = {'run_time':now.isoformat().replace('+00:00','Z'), 'first_run_date':min(dates) if dates else '', 'days_with_success':len(dates), 'successful_dates':sorted(dates), 'open':sum(r['status']=='open' for r in rows), 'new_today':sum(r['first_seen']==date and r['first_run']=='false' for r in rows), 'removed_today':sum(r['removed_date']==date for r in rows), 'sources':results}
    (ROOT/'data/status.json').write_text(json.dumps(status, indent=2)+'\n')
    if not dates: raise RuntimeError('No source produced a raw file')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command', choices=['collect','build']); args=parser.parse_args()
    collect() if args.command=='collect' else build()
