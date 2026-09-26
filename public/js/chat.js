const thread = document.getElementById("thread");
const home = document.getElementById("home");
const messages = document.getElementById("messages");
const chipsBox = document.getElementById("chips");
const form = document.getElementById("form");
const input = document.getElementById("input");
const sidebar = document.getElementById("sidebar");
const scrim = document.getElementById("scrim");
const nlpToggle = document.getElementById("nlpToggle");

// the server is stateless, so we keep the conversation state here and send it back each time
let state = null;
let chips = [];
let busy = false;
const sessionId = Math.random().toString(36).slice(2);

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

// **bold**, *italic* and new lines
function format(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/\*(.+?)\*/g, "<i>$1</i>")
    .replace(/\n/g, "<br>");
}

function addUser(text) {
  messages.insertAdjacentHTML("beforeend", `<div class="msg user"><div class="bubble">${escapeHtml(text)}</div></div>`);
}

function reportCard(msg) {
  const rows = msg.fields.map((f) => `
    <div class="row">${icon(f.icon)}<span>${f.label}</span><b>${escapeHtml(f.value)}</b></div>`).join("");
  return `
    <div class="report">
      <div class="report-head"><span class="pill ${msg.kind}">${msg.kind}</span>${msg.kind === "lost" ? "Lost" : "Found"} item report</div>
      ${rows}
      <div class="report-actions">
        <button class="btn primary" data-action="confirm">Confirm</button>
        <button class="btn" data-action="edit">Edit</button>
      </div>
    </div>`;
}

function ticket(msg) {
  return `
    <div class="ticket ${msg.kind}">
      <small>Reference code · ${escapeHtml(msg.item)}</small>
      <code>${escapeHtml(msg.ref_code)}</code>
    </div>`;
}

function matchList(msg) {
  return `<div class="matches">` + msg.items.map((m) => `
    <div class="match">
      <b>${escapeHtml(m.item)}${m.color ? " · " + escapeHtml(m.color) : ""}</b>
      <div>${icon("pin")}${escapeHtml(m.location)}</div>
      <div>${icon("calendar")}${escapeHtml(m.date)}</div>
      <small>${escapeHtml([m.ref_code, ...m.reasons].join(" · "))}</small>
    </div>`).join("") + `</div>`;
}

// one line showing what the nlp picked up, for the class demo
function nlpLine(nlp) {
  if (!nlp) return "";
  const parts = [nlp.method];
  if (nlp.intent) parts.push(nlp.confidence ? `${nlp.intent} ${Math.round(nlp.confidence * 100)}%` : nlp.intent);
  for (const [key, value] of Object.entries(nlp.found || {})) parts.push(`${key}: ${value}`);
  if (nlp.faq) parts.push(`faq: ${nlp.faq}`);
  return `<div class="nlp">NLP · ${escapeHtml(parts.join(" · "))}</div>`;
}

function addBot(reply) {
  let html = "";
  for (const m of reply.messages) {
    if (m.type === "text") html += `<div class="text">${format(m.text)}</div>`;
    if (m.type === "report") html += reportCard(m);
    if (m.type === "ticket") html += ticket(m);
    if (m.type === "matches") html += matchList(m);
  }
  messages.insertAdjacentHTML("beforeend", `
    <div class="msg bot">
      <img class="avatar" src="img/nu-logo.png" alt="">
      <div class="bot-body">${html}${nlpLine(reply.nlp)}</div>
    </div>`);
}

function showChips(list) {
  // confirm/edit are already buttons on the report card
  chips = list.filter((c) => c.action !== "confirm" && c.action !== "edit");
  chipsBox.innerHTML = chips.map((c, i) => `<button class="chip" data-chip="${i}">${escapeHtml(c.label)}</button>`).join("");
}

async function send({ text, action, label }) {
  if (busy) return;
  busy = true;
  home.hidden = true;
  chipsBox.innerHTML = "";
  // old report cards shouldn't be clickable anymore
  document.querySelectorAll(".report-actions").forEach((el) => el.remove());

  addUser(text || label);
  messages.insertAdjacentHTML("beforeend", `<div class="msg bot" id="typing"><img class="avatar" src="img/nu-logo.png" alt=""><div class="dots"><i></i><i></i><i></i></div></div>`);
  scrollDown();

  let reply;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, action, state, session_id: sessionId }),
    });
    if (!res.ok) throw new Error(res.status);
    reply = await res.json();
    state = reply.state;
  } catch (err) {
    reply = { messages: [{ type: "text", text: "Couldn't reach the server. Please try again." }], chips: [] };
  }

  document.getElementById("typing").remove();
  addBot(reply);
  showChips(reply.chips);
  saveTickets(reply.messages);
  busy = false;
  scrollDown();
}

function scrollDown() {
  thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" });
}

// tickets are saved in the browser so students can find their codes later
function saveTickets(msgs) {
  const saved = JSON.parse(localStorage.getItem("findit.tickets") || "[]");
  for (const m of msgs) {
    if (m.type === "ticket") saved.unshift({ code: m.ref_code, item: m.item, kind: m.kind });
  }
  localStorage.setItem("findit.tickets", JSON.stringify(saved.slice(0, 10)));
  showTickets();
}

function showTickets() {
  const saved = JSON.parse(localStorage.getItem("findit.tickets") || "[]");
  document.getElementById("tickets").innerHTML = saved.length
    ? saved.map((t, i) => `
      <li>
        <span class="dot ${t.kind}"></span>${escapeHtml(t.item)}<code>${escapeHtml(t.code)}</code>
        <button class="remove" data-remove="${i}" aria-label="Remove ticket ${escapeHtml(t.code)}" title="Remove from list">×</button>
      </li>`).join("")
    : `<li class="empty">Reports you file show up here.</li>`;
}

// removes the ticket from this list only, the report itself stays with the office
document.getElementById("tickets").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-remove]");
  if (!btn) return;
  const saved = JSON.parse(localStorage.getItem("findit.tickets") || "[]");
  const ticket = saved[btn.dataset.remove];
  if (!confirm(`Remove ${ticket.code} from your tickets?`)) return;
  saved.splice(btn.dataset.remove, 1);
  localStorage.setItem("findit.tickets", JSON.stringify(saved));
  showTickets();
});

function newChat() {
  state = null;
  messages.innerHTML = "";
  chipsBox.innerHTML = "";
  home.hidden = false;
  toggleSidebar(false);
}

function toggleSidebar(open) {
  sidebar.classList.toggle("open", open);
  scrim.classList.toggle("show", open);
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  input.style.height = "auto";
  send({ text });
});

input.addEventListener("keydown", (e) => {
  // enter sends, shift+enter is a new line
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";
});

chipsBox.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-chip]");
  if (!btn) return;
  const chip = chips[btn.dataset.chip];
  if (chip.text) send({ text: chip.text });
  else send({ action: chip.action, label: chip.label });
});

// sidebar links, home cards and the confirm/edit buttons all use data-action
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-action]");
  if (!btn) return;
  const label = btn.querySelector("strong")?.textContent || btn.textContent.trim();
  toggleSidebar(false);
  send({ action: btn.dataset.action, label });
});

document.getElementById("newChat").addEventListener("click", newChat);
document.getElementById("newChatTop").addEventListener("click", newChat);
document.getElementById("menuBtn").addEventListener("click", () => toggleSidebar(true));
scrim.addEventListener("click", () => toggleSidebar(false));

nlpToggle.addEventListener("change", () => {
  document.body.classList.toggle("hide-nlp", !nlpToggle.checked);
});

showTickets();
