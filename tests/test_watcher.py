import gzip
import json
import csv
import watcher

def test_conversions():
    samples = [
      ({'id':'g','name':'G','type':'greenhouse'}, {'jobs':[{'id':1,'title':'Portfolio Analyst','location':{'name':'Boston'},'departments':[{'name':'Investments'}], 'absolute_url':'https://example.com/1','first_published':'2025-01-01T00:00:00Z'}]}, '1','Boston','Investments','2025-01-01'),
      ({'id':'l','name':'L','type':'lever'}, [{'id':'abc','text':'Investment Analyst','categories':{'location':'NY','team':'Research'},'hostedUrl':'https://example.com/2','createdAt':1735689600000}], 'abc','NY','Research','2025-01-01'),
      ({'id':'w','name':'W','type':'workday','host':'test.wd1','board':'External'}, {'pages':[{'jobPostings':[{'title':'ETF Analyst','externalPath':'/job/City/ETF_R-123','locationsText':'Chicago'}]}]}, 'R-123','Chicago','','')]
    for source, data, sid, loc, dep, date in samples:
        row=watcher.normalize(source,data)[0]
        assert (row['source_id'],row['location'],row['department'],row['posted_date'])==(sid,loc,dep,date)
        assert row['posting_id']==source['id']+':'+sid and row['in_role']=='true'

def test_title_rules():
    for title in ['Portfolio Analyst','Investment Solutions Associate','ETF Research Analyst','Fixed Income Analyst','Wealth Management Analyst']:
        assert watcher.in_role(title)
    for title in ['Investment Accounting Analyst','Portfolio Software Engineer','Sales Associate','Recruiter']:
        assert not watcher.in_role(title)

def test_history_removals_failures_and_reappearance(tmp_path, monkeypatch):
    monkeypatch.setattr(watcher,'ROOT',tmp_path)
    monkeypatch.setattr(watcher,'SOURCES',[{'id':'g','name':'G','type':'greenhouse'},{'id':'h','name':'H','type':'greenhouse'}])
    def write(day, source, ids):
        folder=tmp_path/'data'/'raw'/day; folder.mkdir(parents=True,exist_ok=True)
        with gzip.open(folder/(source+'.json.gz'),'wt') as f: json.dump({'jobs':[{'id':i,'title':'Portfolio Analyst','absolute_url':f'https://example.com/{i}'} for i in ids]},f)
    write('2026-01-01','g',[1]); write('2026-01-01','h',[3]); write('2026-01-02','g',[1,2]); write('2026-01-03','g',[2]); write('2026-01-04','g',[1])
    h,days=watcher.build()
    assert h['g:1']['first_run']=='true' and h['g:1']['first_seen']=='2026-01-01' and h['g:1']['last_seen']=='2026-01-04' and h['g:1']['status']=='open' and not h['g:1']['removed_date']
    assert h['g:2']['first_run']=='false' and h['g:2']['removed_date']=='2026-01-04' and h['g:2']['last_seen']=='2026-01-03'
    assert h['h:3']['status']=='open' and len(days)==4
    first=(tmp_path/'data/history.csv').read_bytes(); watcher.build(); assert (tmp_path/'data/history.csv').read_bytes()==first
