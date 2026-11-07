import {$, load, bars, counts, dayDiff, normalizeLocation, escapeHTML as e, number, showError} from './common.js?v=9';
try {
  const {status, rows} = await load();
  const last = status.run_time.slice(0,10);
  const open = rows.filter(row => row.status === 'open');
  const known = rows.filter(row => row.first_run === 'false');
  const removed = rows.filter(row => row.removed_date);
  const durations = removed.filter(row => row.first_run === 'false').map(row => dayDiff(row.first_seen,row.removed_date)).sort((a,b) => a-b);
  const median = durations.length ? (durations[Math.floor((durations.length-1)/2)] + durations[Math.floor(durations.length/2)])/2 : null;
  const eligible = known.filter(row => dayDiff(row.first_seen,last) >= 7);
  const quick = eligible.filter(row => row.removed_date && dayDiff(row.first_seen,row.removed_date) <= 7);
  const sources = Object.fromEntries(status.sources.map(source => [source.name,source]));
  const dateCounts = (items,key) => {
    const values = Object.fromEntries(counts(items,row => row[key]));
    return [...new Set([...(status.successful_dates || []),...Object.keys(values)])].sort().map(day => [day,values[day] || 0]);
  };
  const daily = dateCounts(known,'first_seen'), roles = Object.fromEntries(dateCounts(known.filter(row => row.in_role === 'true'),'first_seen'));
  const max = Math.max(1,...daily.map(day => day[1]));
  const roleMax = Math.max(1,...Object.values(roles));
  const columns = daily.map(([date,value]) => `<div class="day-column" title="${e(date)}: ${number(value)} new, ${number(roles[date] || 0)} matching roles"><div class="column-group"><div class="column" style="height:${value/max*100}%"></div><div class="column role-column" style="height:${(roles[date] || 0)/roleMax*100}%"></div></div><span>${e(new Date(date+'T12:00:00Z').toLocaleDateString(undefined,{month:'short',day:'numeric',timeZone:'UTC'}))}</span></div>`).join('');
  const employers = counts(open,row => row.employer).map(([name,value]) => [sources[name] && !sources[name].ok ? `${name} · stale` : name,value]);
  const top = employers.slice(0,15), remainder = employers.slice(15).reduce((sum,item) => sum + item[1],0);
  if (remainder) top.push(['All others',remainder]);
  const locations = counts(open.filter(row => normalizeLocation(row.location) !== 'Location not specified'),row => normalizeLocation(row.location)).slice(0,10);
  const card = (heading,body,chart) => `<section class="chart-card"><h2>${heading}</h2>${chart || ''}<p>${body}</p></section>`;
  const durationText = median === null ? 'Not yet available' : `${median} ${median === 1 ? 'day' : 'days'}`;
  $('#market').innerHTML = card(`${number(known.length)} new postings observed`, 'Excludes each source’s initial snapshot. Matching roles use a separate scale to show their trend; hover for exact counts.', `<div class="legend"><span>All postings</span><span>Matching roles (own scale)</span></div><div class="daily-chart">${columns}</div>`) +
    card(`${number(removed.length)} postings currently removed`, 'Uses the most recent removal date; reopened postings are excluded.',bars(dateCounts(removed,'removed_date'),'removed-bar')) +
    card(`${number(open.length)} open postings`, 'Top 15 employers; stale indicates the latest source check failed.',bars(top)) +
    card(`Median observed time open: ${durationText}`, `${number(durations.length)} removed postings with a known first observation. This short history can bias the median downward.`,bars(counts(durations,value => String(value)+' days').sort((a,b) => parseInt(a[0])-parseInt(b[0])))) +
    card(`Removed within seven days: ${eligible.length ? Math.round(quick.length/eligible.length*100)+'%' : 'not yet available'}`, `${number(eligible.length)} postings have enough history for this calculation.`,eligible.length ? bars([['Removed within 7 days',quick.length],['Other eligible postings',eligible.length-quick.length]]) : '') +
    card('Most common locations', 'Locations are normalized where possible; multi-location and unclear entries may remain grouped.',bars(locations));
  $('#asof').textContent = `Calculated from the complete history · ${last} UTC`;
} catch (error) { showError(error); }
