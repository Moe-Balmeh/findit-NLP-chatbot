const $ = (id) => document.getElementById(id);

let data = null;
let tab = "found";
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

// colors come from the css so they switch with dark mode.
// status colors are fixed per status so "Claimed" is always the same color
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

  // legend doubles as the exact numbers, since circle charts are hard to read by eye
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

// changing the dropdown saves right away, then refreshes the numbers and charts
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
