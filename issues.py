"""Publish the dated job-change report and close older daily reports."""
import csv
import json
import os
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def issue_title(day):
    return f'Job Watcher — {day.isoformat()}'


def safe_text(value):
    return str(value).replace('@', '&#64;').replace('[', '(').replace(']', ')')


def listing(rows):
    return '\n'.join(
        f"- [{safe_text(row['title'])}]({row['url']}) — {safe_text(row['employer'])} · {safe_text(row['location'])}"
        for row in rows
    ) or '_None._'


def report_body(status, rows):
    today = status['run_time'][:10]
    new = [row for row in rows if row['first_seen'] == today and row['first_run'] == 'false']
    removed = [row for row in rows if row['removed_date'] == today]
    return (f"UTC run: {status['run_time']}\n\n## New ({len(new)})\n\n{listing(new)}"
            f"\n\n## Removed ({len(removed)})\n\n{listing(removed)}\n\n"
            "First observations of a source are excluded from new postings. Source failures are recorded in data/status.json.")


def api(*args):
    return json.loads(subprocess.check_output(['gh', 'api', *args], text=True))


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    status = json.loads((ROOT / 'data/status.json').read_text())
    today = date.fromisoformat(status['run_time'][:10])
    issues = [issue for page in api(f'repos/{repo}/issues?state=all&per_page=100', '--paginate', '--slurp') for issue in page]
    with (ROOT / 'data/history.csv').open(encoding='utf-8', newline='') as stream:
        body = report_body(status, list(csv.DictReader(stream)))
    chunks = []
    while len(body.encode()) > 50000:
        cut = body.rfind('\n', 0, 20000)
        if cut < 0:
            cut = 20000
        chunks.append(body[:cut])
        body = body[cut:]
    chunks.append(body)
    existing = next((issue for issue in issues if issue['title'] == issue_title(today) and 'pull_request' not in issue), None)
    if existing:
        number = existing['number']
        api(f'repos/{repo}/issues/{number}', '-X', 'PATCH', '-f', f'body={chunks[0]}', '-f', 'state=open')
        for comment in api(f'repos/{repo}/issues/{number}/comments?per_page=100'):
            if comment['body'].startswith('<!-- job-watcher-continuation -->'):
                subprocess.run(['gh', 'api', f"repos/{repo}/issues/comments/{comment['id']}", '-X', 'DELETE'], check=True, stdout=subprocess.DEVNULL)
    else:
        number = api(f'repos/{repo}/issues', '-f', f'title={issue_title(today)}', '-f', f'body={chunks[0]}')['number']
    for chunk in chunks[1:]:
        api(f'repos/{repo}/issues/{number}/comments', '-f', f'body=<!-- job-watcher-continuation -->\n{chunk}')
    for issue in issues:
        if issue['state'] == 'open' and 'pull_request' not in issue and issue['title'].startswith('Job Watcher — ') and issue['title'] != issue_title(today):
            api(f"repos/{repo}/issues/{issue['number']}", '-X', 'PATCH', '-f', 'state=closed')


if __name__ == '__main__':
    main()
