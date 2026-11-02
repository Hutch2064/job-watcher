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

def test_experience_classification():
    classify = watcher.experience_level
    assert classify('Senior Portfolio Analyst', 'No experience required')[0] == 'experienced'
    assert classify('Vice President, Investment Research', '')[0] == 'experienced'
    assert classify('Portfolio Analyst, AVP', '')[0] == 'experienced'
    assert classify('Lead Portfolio Analyst', '')[0] == 'experienced'
    assert classify('Portfolio Analyst', '<p>1-3 years of relevant investment experience</p>')[0] == 'early'
    assert classify('Investment Analyst', '<li>Minimum of 3+ years of relevant experience</li>')[0] == 'experienced'
    assert classify('Investment Analyst', '<li>Two years of experience required</li>')[0] == 'early'
    assert classify('Investment Analyst', '<li>Five years of experience preferred</li>')[0] == 'unknown'
    assert classify('Investment Analyst', 'We have served clients for 30 years.')[0] == 'unknown'
    assert classify('Investment Analyst', 'Experienced candidate with 6 - 8-year post-graduation experience.')[0] == 'experienced'
    assert classify('Investment Analyst', '<p>Experience. 8 years in investment management; 4+ years specializing in active credit.</p>')[0] == 'experienced'
    assert classify('Associate Portfolio Manager', '')[0] == 'unknown'
    assert classify('Portfolio Analyst', '1-2 years of experience required. Minimum 5 years of investment experience required.')[0] == 'experienced'

def test_workday_description_is_reproducible_from_raw():
    source={'id':'w','name':'W','type':'workday','host':'test.wd1','board':'External'}
    job={'title':'Investment Analyst','externalPath':'/job/City/role_R-1','locationsText':'City'}
    raw={'pages':[{'jobPostings':[job]}], 'details':{job['externalPath']:'<p>3-5 years of investment experience required.</p>'}}
    assert watcher.normalize(source,raw)[0]['experience']=='experienced'
    del raw['details']
    assert watcher.normalize(source,raw)[0]['experience']=='unknown'

def test_retry_incomplete_source(monkeypatch):
    calls=[]
    def fetch(source):
        calls.append(1)
        if len(calls)<3: raise ValueError('Incomplete pagination')
        return {'jobs':[]}
    monkeypatch.setattr(watcher,'fetch',fetch)
    monkeypatch.setattr(watcher.time,'sleep',lambda _:None)
    data, rows = watcher.fetch_validated({'id':'g','name':'G','type':'greenhouse'})
    assert len(calls)==3 and rows==[] and data=={'jobs':[]}

def test_early_career_title_signals():
    for title in ['Investment Intern', 'Investment Internship', 'SummerIntern', 'investmentinternship', 'Senior Investment Intern']:
        assert watcher.experience_level(title, '') == ('early', 'Internship in title')
    assert watcher.in_role('InvestmentIntern')
    assert watcher.in_role('PortfolioInternship')
    for title in ['International Investment Analyst', 'Internal Investment Analyst', 'Internet Investment Analyst']:
        assert watcher.experience_level(title, '')[0] == 'unknown'
    for title in ['Investment Summer Analyst', 'Investment Graduate Program']:
        assert watcher.experience_level(title, '')[0] == 'early'
    assert watcher.experience_level('Investment Programming Analyst', '')[0] == 'unknown'
    assert watcher.experience_level('Senior Investment Program Manager', '')[0] == 'experienced'
    assert watcher.experience_level('Investment Summer Program', '5 years of experience required')[0] == 'experienced'
