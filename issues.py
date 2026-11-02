"""Create or update today's dated issue and close the previous day's issue."""
import csv
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

root = Path(__file__).resolve().parent
repo = os.environ['GITHUB_REPOSITORY']
today = datetime.now(timezone.utc).date()
def api(*args):
    return json.loads(subprocess.check_output(['gh','api',*args], text=True))
def title(date): return f'Job Watcher — {date.isoformat()}'
issues = api(f'repos/{repo}/issues?state=all&per_page=100')
with (root/'data/history.csv').open(encoding='utf-8', newline='') as f: rows=list(csv.DictReader(f))
status=json.loads((root/'data/status.json').read_text())
def listing(rows):
    return '\n'.join(f"- [{r['title'].replace('[','(').replace(']',')')}]({r['url']}) — {r['employer']} · {r['location']}" for r in rows) or '_None._'
new=[r for r in rows if r['first_seen']==str(today) and r['first_run']=='false']
removed=[r for r in rows if r['removed_date']==str(today)]
body=f"UTC run: {status['run_time']}\n\n## New ({len(new)})\n\n{listing(new)}\n\n## Removed ({len(removed)})\n\n{listing(removed)}\n\nFirst observations of a source are excluded from new postings. Source failures are recorded in data/status.json."
# GitHub has a body size limit. Preserve links by splitting exceptionally large reports into comments.
chunks=[]
while len(body.encode())>50000:
    cut=body.rfind('\n',0,20000)
    if cut<0: cut=20000
    chunks.append(body[:cut]); body=body[cut:]
chunks.append(body)
existing=next((i for i in issues if i['title']==title(today) and 'pull_request' not in i),None)
if existing:
    number=existing['number']; api(f'repos/{repo}/issues/{number}','-X','PATCH','-f',f'body={chunks[0]}','-f','state=open')
    # Remove prior generated continuation comments to make a rerun replace the report.
    for c in api(f'repos/{repo}/issues/{number}/comments?per_page=100'):
        if c['body'].startswith('<!-- job-watcher-continuation -->'):
            subprocess.run(['gh','api',f"repos/{repo}/issues/comments/{c['id']}",'-X','DELETE'],check=True,stdout=subprocess.DEVNULL)
else:
    number=api(f'repos/{repo}/issues','-f',f'title={title(today)}','-f',f'body={chunks[0]}')['number']
for chunk in chunks[1:]: api(f'repos/{repo}/issues/{number}/comments','-f',f'body=<!-- job-watcher-continuation -->\n{chunk}')
yesterday=next((i for i in issues if i['title']==title(today-timedelta(days=1)) and i['state']=='open' and 'pull_request' not in i),None)
if yesterday: api(f"repos/{repo}/issues/{yesterday['number']}",'-X','PATCH','-f','state=closed')
