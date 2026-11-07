import {
  $,
  load,
  list,
  stars,
  saveStars,
  dayDiff,
  normalizeLocation,
  escapeHTML as e,
  showError,
} from "./common.js?v=11";

try {
  const { status, rows } = await load();
  const today = status.run_time.slice(0, 10);
  const saved = stars();
  let applications;
  try {
    applications = JSON.parse(
      localStorage.getItem("watchlist-applications") || "{}",
    );
  } catch {
    applications = {};
  }
  function saveApplications() {
    localStorage.setItem(
      "watchlist-applications",
      JSON.stringify(applications),
    );
  }
  function application(id) {
    return applications[id] || { status: "Saved", note: "", savedDate: "" };
  }
  const filters = [
    "search",
    "location",
    "experience",
    "employer",
    "cover-letter",
    "days",
    "sort",
  ];
  const defaults = {
    search: "",
    location: "",
    experience: "suitable",
    employer: "",
    "cover-letter": "all",
    days: "",
    sort: "newest",
  };
  const parameters = new URLSearchParams(location.search);
  let mode = ["role", "all", "shortlist"].includes(parameters.get("mode"))
    ? parameters.get("mode")
    : "role";
  let limit = 50;
  for (const [id, key] of [
    ["employer", "employer"],
    ["location-options", "location"],
  ]) {
    const values = [
      ...new Set(
        rows
          .filter((row) => row.status === "open")
          .map((row) =>
            key === "location" ? normalizeLocation(row[key]) : row[key],
          )
          .filter(Boolean),
      ),
    ].sort((a, b) => a.localeCompare(b));
    for (const value of values) {
      const option = document.createElement("option");
      option.value = value;
      if (id === "employer") option.textContent = value;
      $("#" + id).append(option);
    }
  }
  for (const id of filters)
    if (parameters.has(id)) $("#" + id).value = parameters.get(id);
  if (
    ["employer", "cover-letter", "days", "sort"].some(
      (id) => $("#" + id).value !== defaults[id],
    )
  )
    $("#more-filters").open = true;
  function matchesSearch(row) {
    const words = $("#search")
      .value.trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    return words.every((word) => row.title.toLowerCase().includes(word));
  }
  function matchesExperience(row) {
    const value = $("#experience").value;
    return (
      value === "all" ||
      (value === "suitable"
        ? row.experience !== "experienced"
        : row.experience === value)
    );
  }
  function matchesCover(row) {
    const value = $("#cover-letter").value;
    return (
      value === "all" ||
      (value === "optional"
        ? ["optional", "not_listed"].includes(row.cover_letter)
        : row.cover_letter === value)
    );
  }
  function matchesOtherFilters(row) {
    return (
      (!$("#employer").value || row.employer === $("#employer").value) &&
      (!$("#location").value ||
        normalizeLocation(row.location)
          .toLowerCase()
          .includes($("#location").value.toLowerCase())) &&
      (!$("#days").value ||
        dayDiff(row.first_seen, today) <= Number($("#days").value))
    );
  }
  function syncURL() {
    const query = new URLSearchParams();
    if (mode !== "role") query.set("mode", mode);
    for (const id of filters)
      if ($("#" + id).value !== defaults[id]) query.set(id, $("#" + id).value);
    history.replaceState(
      null,
      "",
      location.pathname + (query.size ? "?" + query : ""),
    );
  }
  function updateMode() {
    for (const name of ["role", "all", "shortlist"])
      $("#" + name).setAttribute("aria-pressed", String(mode === name));
    $("#star-count").textContent = saved.size;
    $("#shortlist-actions").hidden = mode !== "shortlist";
  }
  function render() {
    updateMode();
    syncURL();
    const matching = rows
      .filter((row) => {
        if (mode === "shortlist") return saved.has(row.posting_id);
        return (
          row.status === "open" &&
          (mode === "all" || row.in_role === "true") &&
          matchesSearch(row) &&
          matchesExperience(row) &&
          matchesCover(row) &&
          matchesOtherFilters(row)
        );
      })
      .sort(
        (a, b) =>
          ($("#sort").value === "oldest"
            ? a.first_seen.localeCompare(b.first_seen)
            : b.first_seen.localeCompare(a.first_seen)) ||
          a.title.localeCompare(b.title),
      );
    $("#result-count").textContent =
      `${matching.length.toLocaleString()} postings`;
    $("#jobs").innerHTML = matching.length
      ? list(matching.slice(0, limit), saved, today)
      : `<div class="empty-state"><h2>${mode === "shortlist" ? "Your shortlist is empty" : "No matching postings"}</h2><p>${mode === "shortlist" ? "Tap the star on any posting to save it here." : "Try a different search or clear your filters."}</p>${mode === "shortlist" ? "" : '<button id="empty-clear">Clear filters</button>'}</div>`;
    if (mode === "shortlist") {
      for (const card of document.querySelectorAll("#jobs .job")) {
        const id = card.querySelector(".star").dataset.id;
        const record = application(id);
        const section = document.createElement("div");
        section.className = "application";
        section.innerHTML = `<label>Application status<select class="application-status"><option>Saved</option><option>Applied</option><option>Interviewing</option><option>Closed</option></select></label><label>Notes<textarea class="application-note" rows="2" placeholder="Add a private note"></textarea></label><span class="muted">${record.savedDate ? "Saved " + e(record.savedDate) : "Saved before tracking was added"}</span>`;
        section.querySelector("select").value = record.status;
        section.querySelector("textarea").value = record.note;
        section.addEventListener("change", (event) => {
          if (event.target.matches(".application-status"))
            record.status = event.target.value;
          if (event.target.matches(".application-note"))
            record.note = event.target.value;
          applications[id] = record;
          saveApplications();
        });
        card.querySelector(".job-content").append(section);
      }
    }
    $("#more").hidden = matching.length <= limit;
    $("#chips").innerHTML =
      mode === "shortlist"
        ? ""
        : filters
            .filter((id) => $("#" + id).value !== defaults[id])
            .map(
              (id) =>
                `<button data-clear="${id}" aria-label="Clear ${e(id)} filter">${e(id)}: ${e($("#" + id).selectedOptions?.[0]?.textContent || $("#" + id).value)} ×</button>`,
            )
            .join("");
  }
  function reset() {
    for (const id of filters) $("#" + id).value = defaults[id];
    mode = "role";
    limit = 50;
    render();
  }
  for (const id of filters)
    $("#" + id).addEventListener("input", () => {
      limit = 50;
      render();
    });
  for (const name of ["role", "all", "shortlist"])
    $("#" + name).onclick = () => {
      mode = name;
      limit = 50;
      render();
    };
  $("#clear").onclick = reset;
  $("#print-shortlist").onclick = () => window.print();
  $("#export-shortlist").onclick = () => {
    const selected = rows.filter((row) => saved.has(row.posting_id));
    const csvCell = (value) =>
      '"' + String(value || "").replaceAll('"', '""') + '"';
    const lines = [
      [
        "Title",
        "Employer",
        "Location",
        "Posting URL",
        "Posting state",
        "Application status",
        "Saved date",
        "Notes",
      ],
      ...selected.map((row) => {
        const a = application(row.posting_id);
        return [
          row.title,
          row.employer,
          row.location,
          row.url,
          row.status,
          a.status,
          a.savedDate,
          a.note,
        ];
      }),
    ];
    const blob = new Blob(
      [lines.map((line) => line.map(csvCell).join(",")).join("\r\n")],
      { type: "text/csv;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob),
      link = document.createElement("a");
    link.href = url;
    link.download = "fieldnote-shortlist.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  $("#more").onclick = () => {
    limit += 50;
    render();
  };
  $("#chips").onclick = (event) => {
    const id = event.target.dataset.clear;
    if (id) {
      $("#" + id).value = defaults[id];
      render();
    }
  };
  $("#jobs").onclick = (event) => {
    if (event.target.id === "empty-clear") {
      reset();
      return;
    }
    const button = event.target.closest(".star");
    if (!button) return;
    const id = button.dataset.id,
      wasSaved = saved.has(id);
    wasSaved ? saved.delete(id) : saved.add(id);
    if (!wasSaved && !applications[id]) {
      applications[id] = {
        status: "Saved",
        note: "",
        savedDate: new Date().toISOString().slice(0, 10),
      };
      saveApplications();
    }
    try {
      saveStars(saved);
    } catch {
      alert("Your browser could not save the shortlist.");
      return;
    }
    button.textContent = saved.has(id) ? "★" : "☆";
    button.setAttribute("aria-pressed", String(saved.has(id)));
    button.closest(".job").classList.toggle("saved", saved.has(id));
    updateMode();
    if (wasSaved) {
      const toast = $("#toast");
      toast.hidden = false;
      toast.innerHTML = "Removed from shortlist. <button>Undo</button>";
      toast.querySelector("button").onclick = () => {
        saved.add(id);
        saveStars(saved);
        toast.hidden = true;
        render();
      };
      setTimeout(() => {
        toast.hidden = true;
      }, 6000);
    }
  };
  render();
} catch (error) {
  showError(error);
}
