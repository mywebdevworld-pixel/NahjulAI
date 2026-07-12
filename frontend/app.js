/* Nahj AI chat frontend — no dependencies, streams SSE from /api/chat. */

const chatEl = document.getElementById("chat");
const formEl = document.getElementById("form");
const inputEl = document.getElementById("input");
const sendEl = document.getElementById("send");
const welcomeEl = document.getElementById("welcome");
const statusEl = document.getElementById("status");

const history = []; // {role, content}
let busy = false;

/* ── Utilities ─────────────────────────────────────────── */

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Minimal markdown: bold, italics, blockquotes, bullet lists, paragraphs,
   plus [Sermon 27]-style citations rendered as clickable chips. */
function renderMarkdown(text) {
  let html = escapeHtml(text);

  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  html = html.replace(
    /\[(Sermon|Letter|Saying)\s+(\d{1,3})\]/gi,
    (_, type, num) =>
      `<button class="cite" data-type="${type.toLowerCase()}" data-num="${num}">${type} ${num}</button>`
  );

  const blocks = html.split(/\n{2,}/);
  return blocks
    .map((block) => {
      const lines = block.split("\n");
      if (lines.every((l) => l.trim().startsWith("&gt;"))) {
        const inner = lines.map((l) => l.replace(/^\s*&gt;\s?/, "")).join("<br>");
        return `<blockquote>${inner}</blockquote>`;
      }
      if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
        const items = lines.map((l) => `<li>${l.replace(/^\s*[-*•]\s+/, "")}</li>`).join("");
        return `<ul>${items}</ul>`;
      }
      if (lines.every((l) => /^\s*\d+\.\s+/.test(l))) {
        const items = lines.map((l) => `<li>${l.replace(/^\s*\d+\.\s+/, "")}</li>`).join("");
        return `<ol>${items}</ol>`;
      }
      return `<p>${block.replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function addMessage(role) {
  welcomeEl?.remove();
  const wrap = document.createElement("div");
  wrap.className = `message ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  wrap.appendChild(bubble);
  chatEl.appendChild(wrap);
  return { wrap, bubble };
}

function scrollToBottom() {
  chatEl.scrollTop = chatEl.scrollHeight;
}

/* ── Passage modal ─────────────────────────────────────── */

const backdrop = document.getElementById("modal-backdrop");
const modalTitle = document.getElementById("modal-title");
const modalBody = document.getElementById("modal-body");
document.getElementById("modal-close").addEventListener("click", closeModal);
backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function closeModal() { backdrop.classList.add("hidden"); }

async function openPassage(type, num) {
  modalTitle.textContent = `${type[0].toUpperCase() + type.slice(1)} ${num}`;
  modalBody.textContent = "Loading…";
  backdrop.classList.remove("hidden");
  try {
    const resp = await fetch(`/api/passage/${type}/${num}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    modalTitle.textContent = data.title ? `${data.ref} — ${data.title}` : data.ref;
    modalBody.textContent = data.text;
  } catch {
    modalBody.textContent = "Could not load this passage.";
  }
}

document.addEventListener("click", (e) => {
  const cite = e.target.closest(".cite, .source-card");
  if (cite?.dataset.type) openPassage(cite.dataset.type, cite.dataset.num);
});

/* ── Sources panel ─────────────────────────────────────── */

function renderSources(wrap, sources) {
  if (!sources.length) return;
  const container = document.createElement("div");
  container.className = "sources";
  const toggle = document.createElement("button");
  toggle.className = "sources-toggle";
  toggle.textContent = `📖 ${sources.length} source${sources.length > 1 ? "s" : ""}`;
  const list = document.createElement("div");
  list.className = "sources-list";
  toggle.addEventListener("click", () => list.classList.toggle("open"));

  const seen = new Set();
  for (const s of sources) {
    if (seen.has(s.doc_id)) continue;
    seen.add(s.doc_id);
    const [type, num] = s.doc_id.split("-");
    const card = document.createElement("div");
    card.className = "source-card";
    card.dataset.type = type;
    card.dataset.num = num;
    const snippet = s.text.length > 160 ? s.text.slice(0, 160) + "…" : s.text;
    card.innerHTML =
      `<span class="source-ref">${escapeHtml(s.ref)}</span>` +
      (s.title ? ` <span>${escapeHtml(s.title)}</span>` : "") +
      `<span class="source-snippet">${escapeHtml(snippet)}</span>`;
    list.appendChild(card);
  }
  container.appendChild(toggle);
  container.appendChild(list);
  wrap.appendChild(container);
}

/* ── Chat streaming ────────────────────────────────────── */

async function sendMessage(text) {
  if (busy || !text.trim()) return;
  busy = true;
  sendEl.disabled = true;

  const userMsg = addMessage("user");
  userMsg.bubble.textContent = text;
  scrollToBottom();

  const assistant = addMessage("assistant");
  assistant.bubble.innerHTML =
    '<div class="typing"><span></span><span></span><span></span></div>';
  scrollToBottom();

  let answer = "";
  let sources = [];

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history }),
    });
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Parse complete SSE events from the buffer
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const eventMatch = raw.match(/^event: (.+)$/m);
        const dataMatch = raw.match(/^data: (.+)$/m);
        if (!eventMatch || !dataMatch) continue;
        const event = eventMatch[1];
        const data = JSON.parse(dataMatch[1]);

        if (event === "sources") {
          sources = data;
        } else if (event === "token") {
          answer += data.t;
          assistant.bubble.innerHTML = renderMarkdown(answer);
          scrollToBottom();
        }
      }
    }
  } catch (err) {
    answer = answer || "Sorry — something went wrong reaching the server. Please try again.";
    assistant.bubble.innerHTML = renderMarkdown(answer);
  }

  if (!answer) {
    answer = "Sorry — no response was generated. Please try again.";
    assistant.bubble.innerHTML = renderMarkdown(answer);
  }

  renderSources(assistant.wrap, sources);
  history.push({ role: "user", content: text });
  history.push({ role: "assistant", content: answer });
  if (history.length > 20) history.splice(0, history.length - 20);

  busy = false;
  sendEl.disabled = false;
  inputEl.focus();
  scrollToBottom();
}

/* ── Wiring ────────────────────────────────────────────── */

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = inputEl.value;
  inputEl.value = "";
  inputEl.style.height = "auto";
  sendMessage(text);
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    formEl.requestSubmit();
  }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
});

document.querySelectorAll(".suggestion").forEach((btn) =>
  btn.addEventListener("click", () => sendMessage(btn.textContent))
);

/* Health indicator */
(async () => {
  try {
    const resp = await fetch("/api/health");
    const h = await resp.json();
    if (h.indexed_chunks > 0 && h.llm_reachable) {
      statusEl.className = "header-status ok";
      statusEl.title = `Ready — ${h.indexed_chunks} passages indexed, LLM: ${h.llm_model}`;
    } else if (h.indexed_chunks > 0) {
      statusEl.className = "header-status degraded";
      statusEl.title = "Index ready, but no LLM reachable — answers will be extractive. Configure .env.";
    } else {
      statusEl.className = "header-status";
      statusEl.title = "Index empty — run the ingestion scripts.";
    }
  } catch {
    statusEl.title = "Backend unreachable";
  }
})();

inputEl.focus();
