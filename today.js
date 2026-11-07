import {
  $,
  load,
  list,
  stars,
  escapeHTML as e,
  number,
  showError,
} from "./common.js?v=17";
try {
  const { status, rows } = await load();
  const date = status.run_time.slice(0, 10);
  const added = rows.filter(
    (row) => row.first_seen === date && row.first_run === "false",
  );
  const removed = rows.filter((row) => row.removed_date === date);
  const relevant = added.filter(
    (row) => row.in_role === "true" && row.experience !== "experienced",
  );
  const early = relevant.filter((row) => row.experience === "early");
  const saved = stars();
  const previousVisit = localStorage.getItem("fieldnote-last-visit");
  const sinceVisit = previousVisit
    ? rows.filter(
        (row) =>
          row.status === "open" &&
          row.in_role === "true" &&
          row.experience !== "experienced" &&
          row.first_run === "false" &&
          row.first_seen > previousVisit.slice(0, 10),
      ).length
    : 0;
  localStorage.setItem("fieldnote-last-visit", new Date().toISOString());
  if ("setAppBadge" in navigator && previousVisit)
    navigator.setAppBadge(sinceVisit).catch(() => {});
  const stale = status.sources.filter((source) => !source.ok);
  const time = new Date(status.run_time);
  $("#updated").innerHTML =
    `Updated <time title="${e(time.toLocaleString())}">${e(time.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }))}</time> · <button class="text-button" id="refresh">Refresh</button>`;
  $("#refresh").onclick = () => location.reload();
  $("#stats").innerHTML = [
    ["Open postings", status.open],
    ["New today", status.new_today],
    ["Removed today", status.removed_today],
    ["Successful days", status.days_with_success],
  ]
    .map(
      ([label, value]) =>
        `<div class="stat"><strong>${number(value)}</strong><span>${e(label)}</span></div>`,
    )
    .join("");
  $("#brief").textContent =
    `${number(relevant.length)} new postings match your role and early-career filter today; ${number(early.length)} show an early-career signal.` +
    (previousVisit
      ? ` ${number(sinceVisit)} appeared after your last visit’s UTC date.`
      : "");
  $("#new").innerHTML = relevant.length
    ? list(relevant.slice(0, 8), saved, date)
    : '<p class="empty">No new matching postings today.</p>';
  $("#all-new").innerHTML =
    list(added, saved, date) || '<p class="empty">No new postings.</p>';
  $("#removed").innerHTML =
    list(removed, saved, date) || '<p class="empty">No removed postings.</p>';
  $("#health-summary").textContent =
    `${stale.length} sources unavailable or suspect`;
  $("#sources").innerHTML = [...status.sources]
    .sort((a, b) => Number(a.ok) - Number(b.ok) || a.name.localeCompare(b.name))
    .map(
      (source) =>
        `<div class="source"><strong>${e(source.name)}</strong><span class="${source.ok ? "healthy" : "error"}">${source.ok ? "Checked" : source.suspect ? "Suspect" : "Unavailable"}</span><span>Last successful check: ${e(source.last_success || (source.ok ? date : "Not available"))}</span>${source.error ? `<span>${e(source.error)}</span>` : ""}${source.warning ? `<span>${e(source.warning)}</span>` : ""}${
          source.observed_dates
            ? `<span class="health-strip" aria-label="Saved observations over recent dates">${(
                status.successful_dates || []
              )
                .slice(-14)
                .map(
                  (day) =>
                    `<i class="${source.observed_dates.includes(day) ? "observed" : "unobserved"}" title="${e(day)}: ${source.observed_dates.includes(day) ? "snapshot saved" : "no snapshot on record"}"></i>`,
                )
                .join("")}</span>`
            : ""
        }</div>`,
    )
    .join("");
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".star");
    if (!button) return;
    saved.has(button.dataset.id)
      ? saved.delete(button.dataset.id)
      : saved.add(button.dataset.id);
    localStorage.setItem("watchlist-stars", JSON.stringify([...saved]));
    button.textContent = saved.has(button.dataset.id) ? "★" : "☆";
    button.setAttribute("aria-pressed", saved.has(button.dataset.id));
    button
      .closest(".job")
      .classList.toggle("saved", saved.has(button.dataset.id));
  });
} catch (error) {
  showError(error);
}
