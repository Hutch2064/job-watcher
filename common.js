export const $ = (selector, root = document) => root.querySelector(selector);
export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
export const number = value => Number(value || 0).toLocaleString();

export function parseCSV(text) {
  const records = []; let row = [], field = '', quoted = false;
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') { field += '"'; index++; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ',') { row.push(field); field = ''; }
    else if (char === '\n') { row.push(field); records.push(row); row = []; field = ''; }
    else if (char !== '\r') field += char;
  }
  if (field || row.length) { row.push(field); records.push(row); }
  const keys = records.shift() || [];
  return records.filter(record => record.length === keys.length).map(record => Object.fromEntries(keys.map((key, index) => [key, record[index]])));
}

export async function load() {
  const cache = await caches.open('fieldnote-data');
  const oldStatus = await cache.match('data/status.json') || await caches.match('data/status.json');
  const oldHistory = await cache.match('data/history.csv') || await caches.match('data/history.csv');
  let status, history, offline = false;
  try {
    const response = await fetch('data/status.json', {cache: 'no-cache'});
    if (!response.ok) throw Error('Status unavailable');
    status = await response.clone().json();
    const previous = oldStatus ? await oldStatus.clone().json() : null;
    if (oldHistory && previous?.run_time === status.run_time) history = oldHistory;
    else {
      history = await fetch('data/history.csv', {cache: 'no-cache'});
      if (!history.ok) throw Error('History unavailable');
      await cache.put('data/history.csv', history.clone());
    }
    await cache.put('data/status.json', response);
  } catch (error) {
    if (!oldStatus || !oldHistory) throw error;
    status = await oldStatus.json(); history = oldHistory; offline = true;
  }
  const notice = $('#offline');
  if (notice) {
    notice.hidden = !offline && navigator.onLine;
    notice.textContent = `Offline or unavailable: showing data from ${new Date(status.run_time).toLocaleString()}.`;
  }
  return {status, rows: parseCSV(await history.text())};
}
export function showError(error) {
  const target = $('#content');
  target.innerHTML = `<div class="error-block"><h2>Could not load the latest data</h2><p>Check your connection and try again.</p><button onclick="location.reload()">Try again</button></div>`;
  console.error(error);
}
export function stars() {
  try { return new Set(JSON.parse(localStorage.getItem('watchlist-stars') || '[]')); }
  catch { return new Set(); }
}
export function saveStars(set) { localStorage.setItem('watchlist-stars', JSON.stringify([...set])); }
export function dayDiff(a, b) { return Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000); }
export function relativeDate(date, today) {
  const days = dayDiff(date, today);
  return days === 0 ? 'Today' : days === 1 ? '1 day ago' : days > 1 ? `${days} days ago` : date;
}
export function normalizeLocation(value) {
  let location = (value || '').trim();
  if (!location || /^\d+\s+locations?$/i.test(location)) return 'Location not specified';
  location = location.replace(/,\s*(United States of America|United States|USA)$/i, '').replace(/,\s*Canada$/i, ', Canada');
  const states = {'New York':'NY','Massachusetts':'MA','California':'CA','Illinois':'IL','Texas':'TX','New Jersey':'NJ','Connecticut':'CT','Pennsylvania':'PA','Florida':'FL','Colorado':'CO','Washington':'WA'};
  for (const [name, code] of Object.entries(states)) location = location.replace(new RegExp(`,\\s*${name}$`, 'i'), `, ${code}`);
  return location;
}
export function job(row, saved = new Set(), today = '') {
  const e = escapeHTML, selected = saved.has(row.posting_id);
  const url = /^https:\/\//i.test(row.url) ? e(row.url) : '#';
  const experience = {early:'Early career', unknown:'Needs review', experienced:'More experienced'}[row.experience];
  const cover = {required:'Cover letter required', optional:'Cover letter optional'}[row.cover_letter];
  return `<article class="job ${selected ? 'saved' : ''}"><div class="job-content"><div class="job-title"><h3><a href="${url}" target="_blank" rel="noopener noreferrer">${e(row.title)} <span aria-hidden="true">↗</span></a></h3><button class="star" data-id="${e(row.posting_id)}" aria-label="${selected ? 'Remove from' : 'Add to'} shortlist: ${e(row.title)}" aria-pressed="${selected}">${selected ? '★' : '☆'}</button></div><div class="meta">${e(row.employer)} · ${e(normalizeLocation(row.location))} · ${e(relativeDate(row.first_seen,today))}</div><div class="badges">${row.status === 'removed' ? '<span class="badge removed">Removed</span>' : ''}${row.first_seen === today && row.first_run === 'false' ? '<span class="badge positive">New</span>' : ''}${experience ? `<span class="badge ${e(row.experience)}" title="${e(row.experience_reason)}">${e(experience)}</span>` : ''}${cover ? `<span class="badge" title="${e(row.cover_letter_reason)}">${e(cover)}</span>` : ''}</div>${row.duty_excerpt ? `<details class="duties"><summary>View duties</summary><p>${e(row.duty_excerpt)}</p></details>` : ''}</div></article>`;
}
export function list(rows, saved, today) { return rows.map(row => job(row, saved, today)).join(''); }
export const counts = (items, key) => Object.entries(items.reduce((result, item) => { const value = key(item); result[value] = (result[value] || 0) + 1; return result; }, {})).sort((a,b) => b[1] - a[1]);
export function bars(data, type = '') {
  const max = Math.max(1, ...data.map(item => item[1]));
  return data.map(([label, value]) => `<div class="bar-row" title="${escapeHTML(label)}: ${number(value)}"><span>${escapeHTML(label)}</span><div class="bar-space">${value ? `<div class="bar ${type}" style="width:${value/max*100}%"></div>` : ''}</div><strong>${number(value)}</strong></div>`).join('');
}
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(console.error);
