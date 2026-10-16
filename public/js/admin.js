const $ = (id) => document.getElementById(id);

let data = null;
let tab = "found";
let evalLoaded = false;
const charts = {};

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

async function api(path, body) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(path, options);
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(json.error || "Something went wrong");
    err.status = res.status;
    throw err;
  }
  return json;
}

async function load() {
  try {
    data = await api("/api/admin/data");
  } catch (err) {
    if (err.status === 401) return showLogin();
    return alert(err.message);
  }
  $("loginView").hidden = true;
  $("dashView").hidden = false;
  render();
  if (!evalLoaded) loadEvaluation();
}

function showLogin() {
  $("dashView").hidden = true;
  $("loginView").hidden = false;
  $("email").focus();
}

function render() {
  const s = data.summary;
  $("who").textContent = data.admin;
  $("statLost").textContent = s.lost;
  $("statFound").textContent = s.found;
  $("statClaimed").textContent = s.claimed;
  $("statRate").textContent = s.return_rate + "%";

  drawDonut("Status", data.charts.status);
  drawDonut("Items", data.charts.items);
  drawDonut("Places", data.charts.places);
  renderTable();
}

// colors come from css so they follow dark mode, each status has a fixed color
function color(name) {
  return getComputedStyle(document.body).getPropertyValue(name).trim();
}
const STATUS_COLORS = { "Waiting for drop-off": "--c4", "At the office": "--c1", "Claimed": "--c3", "Disposed": "--other" };

function sliceColors(key, labels) {
  return labels.map((label, i) => {
    if (key === "Status") return color(STATUS_COLORS[label]);
    return label === "Other" ? color("--other") : color(`--c${i + 1}`);
  });
}

function drawDonut(key, chart) {
  const total = chart.values.reduce((a, b) => a + b, 0);
  const colors = sliceColors(key, chart.labels);
  $("total" + key).innerHTML = `<b>${total}</b><span>total</span>`;

  // legend shows the exact counts and percentages
  $("legend" + key).innerHTML = total
    ? chart.labels.map((label, i) => `
        <li><i style="background:${colors[i]}"></i>${escapeHtml(label)}
        <b>${chart.values[i]}</b><span>${Math.round((100 * chart.values[i]) / total)}%</span></li>`).join("")
    : `<li class="empty">No reports yet</li>`;

  if (charts[key]) charts[key].destroy();
  charts[key] = new Chart($("chart" + key), {
    type: "doughnut",
    data: {
      labels: chart.labels,
      datasets: [{
        data: total ? chart.values : [1],
        backgroundColor: total ? colors : [color("--line")],
        borderColor: color("--card"),
        borderWidth: 2,
        hoverOffset: 4,
      }],
    },
    options: {
      cutout: "65%",
      plugins: { legend: { display: false }, tooltip: { enabled: total > 0 } },
    },
  });
}

function renderTable() {
  const rows = data[tab];
  const statuses = data[tab === "found" ? "found_status" : "lost_status"];
  const q = $("search").value.trim().toLowerCase();
  const shown = rows.filter((r) =>
    [r.ref_code, r.item, r.details, r.location].join(" ").toLowerCase().includes(q));

  $("countFound").textContent = data.found.length;
  $("countLost").textContent = data.lost.length;

  $("rows").innerHTML = shown.length ? shown.map((r) => `
    <tr>
      <td><code>${escapeHtml(r.ref_code)}</code></td>
      <td>${escapeHtml(r.item)}</td>
      <td class="muted">${escapeHtml(r.details) || "-"}</td>
      <td>${escapeHtml(r.location)}</td>
      <td class="nowrap">${escapeHtml(r.date)}</td>
      <td>${r.matches.map((m) => `<code class="match">${escapeHtml(m)}</code>`).join(" ") || '<span class="muted">-</span>'}</td>
      <td>
        <select class="status ${r.status}" data-id="${r.id}">
          ${Object.entries(statuses).map(([value, label]) =>
            `<option value="${value}" ${value === r.status ? "selected" : ""}>${label}</option>`).join("")}
        </select>
      </td>
    </tr>`).join("")
    : `<tr><td colspan="7" class="empty">Nothing here yet.</td></tr>`;
}

// loaded separately so the dashboard doesn't wait on it
async function loadEvaluation() {
  try {
    renderEvaluation(await api("/api/admin/evaluation"));
    evalLoaded = true;
  } catch (err) {
    $("evalStatus").textContent = "Couldn't load the evaluation: " + err.message;
  }
}

const NICE = { REPORT_LOST: "Report lost", REPORT_FOUND: "Report found", SEARCH_ITEM: "Search", GENERAL_INQUIRY: "Question" };
const nice = (intent) => NICE[intent] || intent;

function facts(id, list) {
  $(id).innerHTML = list.map(([label, value]) => `<li>${label}<b>${value}</b></li>`).join("");
}

function renderEvaluation(ev) {
  const { intent } = ev;
  $("evalStatus").hidden = true;
  $("evalBody").hidden = false;

  $("evAccuracy").textContent = intent.accuracy + "%";
  $("evAccuracyNote").textContent = `${intent.total} handwritten messages`;
  $("evPrecision").textContent = intent.precision + "%";
  $("evRecall").textContent = intent.recall + "%";
  $("evF1").textContent = intent.f1 + "%";

  $("evPerClass").innerHTML = intent.per_class.map((c) => `
    <tr><td>${nice(c.intent)}</td><td>${c.precision}%</td><td>${c.recall}%</td><td>${c.f1}%</td><td>${c.support}</td></tr>`).join("")
    + `<tr class="avg"><td>Macro average</td><td>${intent.precision}%</td><td>${intent.recall}%</td><td>${intent.f1}%</td><td>${intent.total}</td></tr>`;

  facts("evIntentFacts", [
    ["Average confidence", intent.avg_confidence + "%"],
    [`Confident enough to act on (≥ ${intent.threshold}%)`, intent.coverage + "%"],
    ["Accuracy when confident", intent.confident_accuracy + "%"],
  ]);

  // shade scales with count: green = correct, red = mistakes
  const most = Math.max(...intent.matrix.flat(), 1);
  $("evMatrix").innerHTML = `
    <tr><th>Real ↓ / Predicted →</th>${intent.labels.map((l) => `<th>${nice(l)}</th>`).join("")}</tr>
    ${intent.matrix.map((row, i) => `
      <tr><th>${nice(intent.labels[i])}</th>${row.map((n, j) => {
        const shade = n ? 15 + Math.round((70 * n) / most) : 0;
        const tint = i === j ? "--c3" : "--bad";
        return `<td style="background:color-mix(in srgb, var(${tint}) ${shade}%, transparent)">${n}</td>`;
      }).join("")}</tr>`).join("")}`;

}

$("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("loginError").textContent = "";
  try {
    await api("/api/admin/login", { email: $("email").value, password: $("password").value });
    $("password").value = "";
    load();
  } catch (err) {
    $("loginError").textContent = err.message;
  }
});

$("logoutBtn").addEventListener("click", async () => {
  await api("/api/admin/logout", {});
  showLogin();
});

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelector(".tab.active").classList.remove("active");
    btn.classList.add("active");
    tab = btn.dataset.tab;
    renderTable();
  });
});

$("search").addEventListener("input", renderTable);

// save the new status, then reload the dashboard
$("rows").addEventListener("change", async (e) => {
  const select = e.target.closest("select.status");
  if (!select) return;
  select.disabled = true;
  try {
    await api("/api/admin/status", { kind: tab, id: select.dataset.id, status: select.value });
    await load();
  } catch (err) {
    alert(err.message);
    select.disabled = false;
  }
});

load();
