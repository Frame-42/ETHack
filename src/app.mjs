import {
  DIMENSIONS,
  DEFAULT_WEIGHTS,
  EXTENDED_WEIGHTS,
  normalizedWeights,
  rankCompanies,
  peerPercentile,
  csvText,
} from "./model.mjs";
import {
  HOLDINGS,
  THEMES,
  STRESSES,
  allocate,
  stressPortfolio,
} from "./portfolio.mjs";
import { methodologyHTML } from "./methodology.mjs";
const $ = (s) => document.querySelector(s);
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const num = (v) => (v == null ? "—" : Number(v).toFixed(1));
const money = (v) => "$" + (v / 1e6).toFixed(0) + "m";
const state = {
  lens: "core",
  weights: { ...DEFAULT_WEIGHTS },
  mid: 50,
  search: "",
  sector: "",
  coverage: "all",
  sort: "score",
  cell: null,
  limit: 25,
  selected: new Set(),
};
let data,
  ranked = [],
  filtered = [],
  portfolioWeights = Object.fromEntries(
    HOLDINGS.map((h) => [h.ticker, h.weight]),
  );
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 3500);
}
function download(text, name, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function view() {
  const name = ["compare", "portfolio", "method"].includes(
    location.hash.slice(1),
  )
    ? location.hash.slice(1)
    : "compare";
  for (const v of ["compare", "portfolio", "method"])
    $(`#view-${v}`).hidden = v !== name;
  document.querySelectorAll("[data-view]").forEach((a) => {
    a.classList.toggle("active", a.dataset.view === name);
    if (a.dataset.view === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  document.title = `${name === "compare" ? "Company observatory" : name === "portfolio" ? "The $1bn question" : "Method & sources"} — After the Pledge`;
}
function weightsUI() {
  const w = normalizedWeights(state.weights);
  $("#weights").innerHTML = DIMENSIONS.filter(
    (d) => state.lens === "extended" || d.key !== "nature",
  )
    .map(
      (d) =>
        `<div class="weight-row"><label class="weight-label" for="weight-${d.key}"><span title="${escape(d.description)}">${d.label}</span><output id="output-${d.key}">${Math.round(w[d.key] * 100)}%</output></label><input type="range" min="0" max="100" step="5" value="${state.weights[d.key]}" id="weight-${d.key}" data-weight="${d.key}" aria-describedby="output-${d.key}"></div>`,
    )
    .join("");
  $("#lens-note").textContent =
    state.lens === "core"
      ? "Climate and people are available for 217 companies. Nature stays visible but is excluded from this score."
      : "Only 71 companies have all four pillars. A missing nature assessment cannot be treated as zero.";
}
function matrixUI() {
  const rows = data.companies.filter(
    (c) => c.assessment && (!state.sector || c.sector === state.sector),
  );
  const counts = Array.from({ length: 3 }, (_, ctt) =>
    Array.from(
      { length: 6 },
      (_, tpq) =>
        rows.filter((c) => c.assessment.ctt === ctt && c.assessment.tpq === tpq)
          .length,
    ),
  );
  const max = Math.max(1, ...counts.flat());
  let html =
    '<div class="matrix-grid" aria-label="Company counts by WBA plan quality and climate contribution">';
  for (const ctt of [2, 1, 0]) {
    html += `<span class="axis-tick">${ctt}/2</span>`;
    for (let tpq = 0; tpq <= 5; tpq++) {
      const n = counts[ctt][tpq],
        selected = state.cell?.tpq === tpq && state.cell?.ctt === ctt;
      html += `<button class="matrix-cell ${tpq === 0 ? "first" : ""} ${ctt === 0 ? "last-row" : ""} ${selected ? "selected" : ""}" data-tpq="${tpq}" data-ctt="${ctt}" aria-pressed="${selected}" aria-label="Plan quality ${tpq} of 5, contribution ${ctt} of 2: ${n} companies">${n ? `<span class="bubble" style="width:${Math.max(24, 60 * Math.sqrt(n / max))}px;height:${Math.max(24, 60 * Math.sqrt(n / max))}px">${n}</span>` : '<span class="zero-cell">·</span>'}</button>`;
    }
  }
  html +=
    "<span></span>" +
    [0, 1, 2, 3, 4, 5]
      .map((n) => `<span class="axis-tick">${n}/5</span>`)
      .join("") +
    "</div>";
  $("#matrix").innerHTML = html;
  $("#clear-cell").hidden = !state.cell;
}
function applyFilters() {
  filtered = ranked.filter(
    (c) =>
      (!state.search ||
        `${c.name} ${c.tickers.join(" ")}`
          .toLowerCase()
          .includes(state.search.toLowerCase())) &&
      (!state.sector || c.sector === state.sector) &&
      (!state.cell ||
        (c.assessment?.ctt === state.cell.ctt &&
          c.assessment?.tpq === state.cell.tpq)) &&
      (state.coverage === "all" ||
        (state.coverage === "complete" && c.result.complete) ||
        (state.coverage === "partial" && c.assessment && !c.result.complete) ||
        (state.coverage === "unmatched" && !c.assessment)),
  );
  if (state.sort === "name")
    filtered.sort((a, b) => a.name.localeCompare(b.name));
  if (state.sort === "social")
    filtered.sort(
      (a, b) => (b.assessment?.social ?? -1) - (a.assessment?.social ?? -1),
    );
}
function tableUI() {
  applyFilters();
  $("#row-count").textContent =
    `${filtered.length} companies${state.cell ? ` · TPQ ${state.cell.tpq}/5, CTT ${state.cell.ctt}/2` : ""}`;
  $("#empty").hidden = filtered.length > 0;
  $(".table-wrap").hidden = filtered.length === 0;
  $("#company-rows").innerHTML = filtered
    .slice(0, state.limit)
    .map((c) => {
      const a = c.assessment,
        r = c.result;
      return `<tr><td><input type="checkbox" data-compare="${c.cik}" aria-label="Compare ${escape(c.name)}" ${state.selected.has(c.cik) ? "checked" : ""}></td><td class="rank">${c.rank ?? "—"}</td><td><button class="company-name" data-detail="${c.cik}">${escape(c.name)}</button><div class="company-meta">${escape(c.tickers.join(" / "))} · ${escape(c.sector)}</div></td><td>${r.complete ? `<div class="score-box">${num(r.value)}<span class="mini-bar"><i style="width:${r.value}%"></i></span></div>` : `<span class="interval">${num(r.lower)}–${num(r.upper)}</span>`}</td><td class="metric">${a ? `${a.ctt}/2` : "—"}</td><td class="metric">${a ? `${a.tpq}/5` : "—"}</td><td class="metric">${num(a?.social)}</td><td class="metric">${num(a?.nature)}</td><td><span class="pill ${r.complete ? "" : a ? "partial" : "missing"}">${r.complete ? `${r.known}/${r.required} pillars` : a ? `${r.known}/${r.required} · partial` : "Unmatched"}</span></td><td><button class="detail-button" data-detail="${c.cik}" aria-label="Inspect ${escape(c.name)}">↗</button></td></tr>`;
    })
    .join("");
  $("#show-more").hidden = filtered.length <= state.limit;
  $("#show-more").textContent =
    `Show ${Math.min(50, filtered.length - state.limit)} more companies`;
  comparisonUI();
}
function refresh() {
  try {
    ranked = rankCompanies(
      data.companies,
      state.weights,
      state.mid,
      state.lens,
    );
    $("#weight-error").hidden = true;
  } catch (e) {
    $("#weight-error").textContent = e.message;
    $("#weight-error").hidden = false;
    return;
  }
  $("#eligible-count").textContent = ranked.filter(
    (c) => c.result.complete,
  ).length;
  matrixUI();
  tableUI();
}
function comparisonUI() {
  const rows = ranked.filter((c) => state.selected.has(c.cik));
  $("#comparison").hidden = !rows.length;
  $("#comparison").innerHTML =
    `<div class="compare-top"><h3>Side by side · ${rows.length}/3</h3><button class="text-button" id="clear-comparison">Clear selection ×</button></div><div class="compare-grid">${rows.map((c) => `<div class="compare-item"><h3>${escape(c.name)} <span class="muted">${escape(c.ticker)}</span></h3><p class="big-score">${c.result.complete ? num(c.result.value) : `${num(c.result.lower)}–${num(c.result.upper)}`}</p>${DIMENSIONS.map((d) => `<p>${d.label}: <strong>${num(c.result.pillars[d.key])}</strong>${d.key === "nature" && state.lens === "core" ? " (context only)" : ""}</p>`).join("")}<p class="muted">${c.result.complete ? "Rank " + c.rank : "Unranked · incomplete evidence"}</p><button class="text-button" data-detail="${c.cik}">Inspect sources ↗</button></div>`).join("")}</div>`;
}
function details(cik) {
  const c = ranked.find((c) => c.cik === cik),
    a = c.assessment,
    r = c.result,
    range = c.sensitivity[state.lens],
    peer = peerPercentile(c, ranked);
  const w = normalizedWeights(state.weights);
  $("#dialog-content").innerHTML =
    `<p class="eyebrow">COMPANY EVIDENCE FILE / ${escape(c.tickers.join(" · "))}</p><h2 id="dialog-title">${escape(c.name)}</h2><p class="dialog-subtitle">${escape(c.industry)} · CIK ${c.cik}</p><div class="dialog-score">${r.complete ? num(r.value) : `${num(r.lower)}–${num(r.upper)}`} <small>${r.complete ? "/ 100 · our composite" : "possible range · unranked"}</small></div><div class="dialog-metrics">${DIMENSIONS.map((d) => `<div><span>${d.label}${d.key === "nature" && state.lens === "core" ? " · context" : ""}</span><b>${num(r.pillars[d.key])}</b><span>${Math.round(w[d.key] * 100)}% weight${r.pillars[d.key] != null ? ` → ${(w[d.key] * r.pillars[d.key]).toFixed(2)} points` : " · unavailable"}</span></div>`).join("")}</div><div class="dialog-detail"><strong>Read this score correctly</strong><p>${a ? `Original WBA ACT grade: <strong>${escape(a.act_grade)}</strong>. CTT ${a.ctt}/2 is mapped to ${num(r.pillars.contribution)}/100; TPQ ${a.tpq}/5 to ${num(r.pillars.planning)}/100. These are explicit value mappings of ordinal categories.` : "No assessment was matched. This is a data gap, not evidence of poor sustainability."}</p><p>${range ? `Rank sensitivity: <strong>${range.best}–${range.worst}</strong> across 15 predefined weight/mapping combinations, independent of your current sliders. This is not a confidence interval.` : "No sensitivity rank: the required pillars are incomplete."}</p><p>${peer ? `Sector percentile: ${peer.value.toFixed(0)} among ${peer.count} assessed ${escape(c.sector)} peers. Relative standing is not an absolute sustainability threshold.` : "Sector percentile suppressed: incomplete evidence or fewer than 5 eligible peers."}</p></div><div class="dialog-detail"><strong>Source & matching</strong><p>${a ? `<a href="${escape(a.source.url)}" target="_blank" rel="noopener noreferrer">WBA assessment: ${escape(c.wba.name)} ↗</a><br>2026 assessment release; retrieved ${escape(a.source.retrieved_at.slice(0, 10))}. Underlying reporting periods vary.<br>Match: ${escape(c.match_method.replaceAll("_", " "))}.` : "Unmatched against the returned WBA directory using normalized names and reviewed aliases."}</p>${a ? `<p class="source-hash">Source page SHA-256<br>${a.source.sha256}</p>` : ""}</div>${a ? '<div class="dialog-detail"><p>Neither a target nor a policy is a realised emissions reduction. The public profile’s rounded revenue and footprint figures are excluded from scoring because their periods and boundaries cannot be reconciled here.</p></div>' : ""}`;
  $("#company-dialog").showModal();
}
function portfolioUI() {
  $("#view-portfolio").innerHTML =
    `<div class="intro"><div><p class="eyebrow">TOMORROW, NET ZERO BECOMES THE WORLD’S PRIORITY</p><h1>Buy the bottlenecks.</h1></div><p class="intro-note">The fastest transition needs connections, dependable power and less wasted energy. Those are the starting points for this portfolio.</p></div><div class="portfolio-thesis"><div class="big-money">$1 billion</div><p>An illustrative 5–10 year, unlevered mandate: 80% in S&P 500 equities and 20% in short-dated Treasury bills. The allocation is an investment hypothesis. It is not inferred from the sustainability leaderboard.</p></div><div class="section-heading"><h2>Capital, with a job to do</h2><button id="reset-portfolio" class="outline-button">Reset allocation ↺</button></div><div id="allocation-bar" class="allocation-bar"></div><div id="allocation-legend" class="allocation-legend"></div><div class="table-wrap"><table class="portfolio-table"><thead><tr><th>Company / asset</th><th>Weight %</th><th>Capital</th><th>Why it belongs · what can go wrong</th><th>WBA evidence</th></tr></thead><tbody>${HOLDINGS.map(
      (h) => {
        const c = data.companies.find((c) => c.tickers.includes(h.ticker));
        return `<tr><td><strong>${escape(h.name)}</strong><div class="company-meta">${h.ticker}</div></td><td><input class="allocation-input" type="number" min="0" max="100" step="1" value="${h.weight}" data-allocation="${h.ticker}" aria-label="${escape(h.name)} allocation percentage"></td><td class="metric" id="capital-${h.ticker}"></td><td class="thesis">${escape(h.thesis)}<p class="risk">Risk: ${escape(h.risk)}</p><a href="${h.source}" target="_blank" rel="noopener noreferrer">Business source ↗</a></td><td>${h.theme === "reserve" ? '<span class="muted small">Outside equity universe</span>' : c?.assessment ? `<button class="text-button" data-detail="${c.cik}">CTT ${c.assessment.ctt}/2<br>People ${num(c.assessment.social)} ↗</button>` : '<span class="pill missing">Unmatched</span>'}</td></tr>`;
      },
    ).join(
      "",
    )}</tbody></table></div><div id="allocation-status" class="scenario-summary" aria-live="polite"></div><div class="scenario-controls"><label for="stress">Stress the allocation</label><select id="stress">${Object.entries(
      STRESSES,
    )
      .map(([key, s]) => `<option value="${key}">${s.name}</option>`)
      .join(
        "",
      )}</select><span id="stress-value" class="stress-value"></span><button id="export-portfolio" class="outline-button">Download allocation ↓</button></div><p id="stress-assumptions" class="small muted"></p><div class="prose-grid"><div><h2>A commitment does not build a grid.</h2><p>Permits, equipment, skilled workers and finance still constrain the pace of deployment. The IEA’s net-zero roadmap identifies grid expansion, electrification, efficiency and low-emissions generation as essential. These holdings are our interpretation of that physical problem.</p><p><a href="https://www.iea.org/reports/net-zero-roadmap-a-global-pathway-to-keep-the-15-c-goal-in-reach/executive-summary" target="_blank" rel="noopener noreferrer">IEA Net Zero Roadmap, 2023 ↗</a></p></div><div><h2>Price still matters on day one.</h2><p>A credible global announcement can reprice these shares before we trade. The 20% reserve avoids assuming yesterday’s prices are available. Deployment is staged; every purchase needs current valuation, leverage, liquidity and project economics checks that this dataset does not contain.</p></div><div><h2>The uncomfortable part of the table</h2><p>Several holdings have weak WBA assessments; six are unmatched. Their products may help customers decarbonise while their own transition evidence is poor. Keep that conflict visible. Engagement focuses on investment disclosure, supply-chain labor, asset retirement and independently verified outcomes.</p></div><div><h2>What would count as impact?</h2><p>Buying existing shares transfers ownership. It does not establish additional avoided emissions. Prefer new issuance financing additional projects when the reserve is deployed, and report financed output and verified emissions separately from returns. Never net claimed customer savings against the company’s footprint.</p></div></div><div class="method-block"><h2>Rules for the scenario mandate</h2><p>Maximum 8% per company, 35% per theme, at least 10% liquid reserve; no leverage or shorting. The theme limits do not imply sector diversification: this remains concentrated in industrials and utilities. Review quarterly; a 2 percentage-point drift triggers a review, not an automatic trade. Exit a thesis if orders fail to become commissioned assets or material labor/environmental harms remain unresolved.</p><p>Stress shocks are illustrative assumptions applied once to position values. They omit covariance, trading costs, taxes and interest income. No probabilities, expected returns or optimality are claimed.</p></div>`;
  updatePortfolio();
}
function updatePortfolio() {
  const a = allocate(portfolioWeights);
  for (const h of a.rows)
    $(`#capital-${h.ticker}`).textContent = Number.isFinite(h.dollars)
      ? money(h.dollars)
      : "—";
  $("#allocation-bar").innerHTML = a.themes
    .filter((t) => t.weight > 0)
    .map(
      (t) =>
        `<div style="flex:${t.weight};background:${t.color}" title="${t.name}: ${t.weight}%">${t.weight}%</div>`,
    )
    .join("");
  $("#allocation-legend").innerHTML = a.themes
    .map(
      (t) =>
        `<span><i style="background:${t.color}"></i>${t.name} · ${t.weight}%</span>`,
    )
    .join("");
  const evidence = a.rows.reduce(
    (sum, h) =>
      sum +
      (data.companies.find((c) => c.tickers.includes(h.ticker))?.assessment
        ? h.weight
        : 0),
    0,
  );
  $("#allocation-status").textContent = a.valid
    ? `${a.total}% allocated · ${money(1e9)} total · ${evidence}% of the fund has matched WBA assessments. Single-company and theme limits pass.`
    : a.problems.join(" ");
  $("#allocation-status").classList.toggle("error", !a.valid);
  $("#export-portfolio").disabled = !a.valid;
  const key = $("#stress").value,
    s = STRESSES[key];
  $("#stress-value").textContent = a.valid
    ? `${stressPortfolio(a, key).percent.toFixed(1)}% / ${money(stressPortfolio(a, key).change)}`
    : "Balance the allocation first";
  $("#stress-assumptions").textContent =
    "Assumed one-off price changes: " +
    Object.entries(s.shocks)
      .map(([k, v]) => `${THEMES[k].name} ${v > 0 ? "+" : ""}${v}%`)
      .join(" · ") +
    ". These are stress inputs, not forecasts.";
}
function clearFilters() {
  state.search = "";
  state.sector = "";
  state.coverage = "all";
  state.cell = null;
  state.limit = 25;
  $("#search").value = "";
  $("#sector").value = "";
  $("#coverage").value = "all";
  refresh();
}
async function init() {
  const response = await fetch("/data/processed/companies.json");
  if (!response.ok) throw new Error(`Dataset returned HTTP ${response.status}`);
  data = await response.json();
  $("#snapshot-date").textContent = data.metadata.snapshot_date;
  $("#universe-count").textContent = data.metadata.issuers;
  $("#matched-count").textContent = data.metadata.matched;
  $("#sector").insertAdjacentHTML(
    "beforeend",
    data.metadata.sectors
      .map((s) => `<option>${escape(s.sector)}</option>`)
      .join(""),
  );
  weightsUI();
  refresh();
  portfolioUI();
  $("#view-method").innerHTML = methodologyHTML(data.metadata);
  $("#loading").hidden = true;
  view();
  window.addEventListener("hashchange", () => {
    view();
    window.scrollTo(0, 0);
  });
  $("#search").addEventListener("input", (e) => {
    state.search = e.target.value;
    state.limit = 25;
    tableUI();
  });
  for (const key of ["sector", "coverage", "sort"])
    $(`#${key}`).addEventListener("change", (e) => {
      state[key] = e.target.value;
      state.limit = 25;
      refresh();
    });
  $("#lens").addEventListener("change", (e) => {
    state.lens = e.target.value;
    state.weights = {
      ...(state.lens === "core" ? DEFAULT_WEIGHTS : EXTENDED_WEIGHTS),
    };
    state.limit = 25;
    weightsUI();
    refresh();
  });
  $("#ctt-map").addEventListener("change", (e) => {
    state.mid = Number(e.target.value);
    refresh();
  });
  $("#weights").addEventListener("input", (e) => {
    if (!e.target.dataset.weight) return;
    const next = {
      ...state.weights,
      [e.target.dataset.weight]: Number(e.target.value),
    };
    try {
      const w = normalizedWeights(next);
      state.weights = next;
      DIMENSIONS.filter(
        (d) => state.lens === "extended" || d.key !== "nature",
      ).forEach(
        (d) =>
          ($(`#output-${d.key}`).textContent =
            `${Math.round(w[d.key] * 100)}%`),
      );
      refresh();
    } catch (err) {
      e.target.value = state.weights[e.target.dataset.weight];
      toast(err.message);
    }
  });
  $("#reset-weights").addEventListener("click", () => {
    state.weights = {
      ...(state.lens === "core" ? DEFAULT_WEIGHTS : EXTENDED_WEIGHTS),
    };
    state.mid = 50;
    $("#ctt-map").value = "50";
    weightsUI();
    refresh();
  });
  $("#matrix").addEventListener("click", (e) => {
    const b = e.target.closest("[data-tpq]");
    if (!b) return;
    const cell = { tpq: Number(b.dataset.tpq), ctt: Number(b.dataset.ctt) };
    state.cell =
      JSON.stringify(state.cell) === JSON.stringify(cell) ? null : cell;
    state.limit = 25;
    refresh();
  });
  $("#clear-cell").addEventListener("click", () => {
    state.cell = null;
    refresh();
  });
  $("#clear-filters").addEventListener("click", clearFilters);
  $("#show-more").addEventListener("click", () => {
    state.limit += 50;
    tableUI();
  });
  $("#export").addEventListener("click", () => {
    download(
      csvText(filtered),
      `after-the-pledge-${state.lens}-${data.metadata.snapshot_date}.csv`,
    );
    download(
      JSON.stringify(
        {
          lens: state.lens,
          weights: normalizedWeights(state.weights),
          ctt_middle: state.mid,
          filters: {
            search: state.search,
            sector: state.sector,
            coverage: state.coverage,
            cell: state.cell,
          },
          snapshot_sha256: data.metadata.snapshot_sha256,
        },
        null,
        2,
      ),
      "scoring-assumptions.json",
      "application/json",
    );
  });
  document.addEventListener("click", (e) => {
    const detail = e.target.closest("[data-detail]");
    if (detail) details(detail.dataset.detail);
    if (e.target.id === "clear-comparison") {
      state.selected.clear();
      tableUI();
    }
    if (e.target.id === "reset-portfolio") {
      portfolioWeights = Object.fromEntries(
        HOLDINGS.map((h) => [h.ticker, h.weight]),
      );
      portfolioUI();
    }
    if (e.target.id === "export-portfolio") {
      const a = allocate(portfolioWeights);
      if (a.valid)
        download(
          "ticker,weight_percent,dollars,theme\n" +
            a.rows
              .map((h) => `${h.ticker},${h.weight},${h.dollars},${h.theme}`)
              .join("\n"),
          "net-zero-allocation.csv",
        );
    }
  });
  document.addEventListener("change", (e) => {
    if (e.target.dataset.compare) {
      const cik = e.target.dataset.compare;
      if (e.target.checked && state.selected.size >= 3) {
        e.target.checked = false;
        toast("Compare up to three companies. Remove one to add another.");
        return;
      }
      e.target.checked ? state.selected.add(cik) : state.selected.delete(cik);
      comparisonUI();
    }
    if (e.target.dataset.allocation) {
      portfolioWeights[e.target.dataset.allocation] =
        e.target.value === "" ? NaN : Number(e.target.value);
      updatePortfolio();
    }
    if (e.target.id === "stress") updatePortfolio();
  });
  $("#close-dialog").addEventListener("click", () =>
    $("#company-dialog").close(),
  );
  $("#company-dialog").addEventListener("click", (e) => {
    if (e.target === $("#company-dialog")) {
      const r = e.target.getBoundingClientRect();
      if (
        e.clientX < r.left ||
        e.clientX > r.right ||
        e.clientY < r.top ||
        e.clientY > r.bottom
      )
        e.target.close();
    }
  });
}
init().catch((e) => {
  $("#loading").textContent =
    `The dataset could not be loaded. Run npm run build:data, then reload. ${e.message}`;
  console.error(e);
});
