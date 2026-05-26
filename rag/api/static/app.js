"use strict";

// ===== Utils =====
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const escapeHtml = (s) => s == null ? "" : String(s).replace(
  /[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
);

function fmtBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`;
  return `${(n / 1073741824).toFixed(2)} GB`;
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function fmtDateOnly(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("fr-FR", { dateStyle: "short" });
}

function fmtNum(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString("fr-FR");
}

function icon(id, cls = "icon") {
  return `<svg class="${cls}"><use href="#i-${id}"/></svg>`;
}

async function api(path, opts = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...opts });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${r.status}: ${text || r.statusText}`);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

// ===== Toasts =====
function toast(msg, type = "info", ms = 3500) {
  const div = document.createElement("div");
  div.className = `toast ${type}`;
  div.textContent = msg;
  $("#toasts").appendChild(div);
  setTimeout(() => div.remove(), ms);
}

// ===== Modal =====
function showModal(title, htmlBody) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = htmlBody;
  $("#modal").classList.add("show");
}
function closeModal() { $("#modal").classList.remove("show"); }
$("#modal-close").addEventListener("click", closeModal);
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function confirmModal(question, onYes) {
  showModal("Confirmation", `
    <p style="margin:0 0 16px">${escapeHtml(question)}</p>
    <div style="display:flex;justify-content:flex-end;gap:8px">
      <button class="btn" id="cm-no">Annuler</button>
      <button class="btn btn-danger" id="cm-yes">Confirmer</button>
    </div>`);
  $("#cm-no").addEventListener("click", closeModal);
  $("#cm-yes").addEventListener("click", () => { closeModal(); onYes(); });
}

// ===== Tabs =====
$$("nav.tabs button").forEach(btn => {
  btn.addEventListener("click", () => {
    $$("nav.tabs button").forEach(b => b.classList.remove("active"));
    $$(".section").forEach(s => s.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
    onTabChange(btn.dataset.tab);
  });
});

function onTabChange(tab) {
  if (tab === "overview") loadOverview();
  if (tab === "documents") loadDocuments();
  if (tab === "articles") loadArticles();
  if (tab === "inspect") loadInspectFilters();
  if (tab === "system") { loadConfig(); loadLogs(); }
}

// ============================================================
// Overview
// ============================================================
async function loadOverview() {
  try {
    const s = await api("/api/overview");
    $("#ov-doc-chunks").textContent = fmtNum(s.chunks_total);
    $("#ov-docs").textContent = fmtNum(s.unique_docs);
    $("#ov-art-chunks").textContent = fmtNum(s.articles_chunks);
    $("#ov-inbox").textContent = fmtNum(s.inbox_count);

    const dot = ok => ok ? "ok" : "ko";
    $("#ov-services").innerHTML = `
      <span class="status-pill"><span class="dot ${dot(s.ollama_ok)}"></span>Ollama</span>
      <span class="status-pill"><span class="dot ${dot(s.qdrant_ok)}"></span>Qdrant</span>
      <span class="status-pill"><span class="dot ${dot(s.watcher_ok)}"></span>Watcher</span>`;

    const m = s.models || [];
    if (!m.length) {
      $("#ov-models").innerHTML = `<div class="empty">Aucun modèle chargé</div>`;
    } else {
      $("#ov-models").innerHTML = `
        <div class="scroll-x"><table>
          <thead><tr><th>Nom</th><th>Taille</th><th>Modifié</th></tr></thead>
          <tbody>${m.map(x => `
            <tr><td><code>${escapeHtml(x.name)}</code></td>
                <td class="numeric">${fmtBytes(x.size)}</td>
                <td>${fmtDate(x.modified_at)}</td></tr>`).join("")}
          </tbody></table></div>`;
    }
  } catch (e) {
    toast("Erreur chargement overview: " + e.message, "error");
  }
}

// ============================================================
// Documents (PDFs)
// ============================================================
async function loadDocuments() {
  try {
    const data = await api("/api/files");
    $("#doc-inbox-count").textContent = data.inbox.length;
    $("#doc-processed-count").textContent = data.processed.length;

    $("#doc-inbox").innerHTML = data.inbox.length === 0
      ? `<div class="empty">Aucun fichier en attente</div>`
      : renderFileTable(data.inbox, false);

    $("#doc-processed").innerHTML = data.processed.length === 0
      ? `<div class="empty">Aucun document indexé</div>`
      : renderFileTable(data.processed, true);

    bindDocActions();
  } catch (e) { toast("Erreur fichiers: " + e.message, "error"); }
}

function renderFileTable(files, processed) {
  return `
    <div class="scroll-x"><table>
      <thead><tr>
        <th>Nom</th><th>Taille</th><th>Modifié</th>
        ${processed ? "<th>Chunks</th>" : ""}
        <th></th>
      </tr></thead>
      <tbody>${files.map(f => `
        <tr>
          <td>${escapeHtml(f.name)}</td>
          <td class="numeric">${fmtBytes(f.size)}</td>
          <td>${fmtDate(f.mtime)}</td>
          ${processed ? `<td class="numeric">${f.chunks ?? "—"}</td>` : ""}
          <td class="actions"><div class="row-actions">${
            processed ? `
              <button class="btn btn-icon" title="Voir markdown" data-doc-action="view-md" data-file="${escapeHtml(f.name)}">${icon("eye","icon-sm")}</button>
              <button class="btn btn-icon" title="Voir chunks" data-doc-action="view-chunks" data-file="${escapeHtml(f.name)}">${icon("list","icon-sm")}</button>
              <button class="btn btn-icon" title="Réingérer" data-doc-action="reingest" data-file="${escapeHtml(f.name)}">${icon("refresh","icon-sm")}</button>
              <button class="btn btn-icon btn-danger" title="Supprimer" data-doc-action="delete" data-file="${escapeHtml(f.name)}">${icon("trash","icon-sm")}</button>`
            : `
              <button class="btn" data-doc-action="ingest-now" data-file="${escapeHtml(f.name)}">${icon("bolt","icon-sm")} Ingérer</button>`
          }</div></td>
        </tr>`).join("")}
      </tbody></table></div>`;
}

function bindDocActions() {
  $$("[data-doc-action]").forEach(btn => {
    btn.addEventListener("click", () => handleDocAction(btn.dataset.docAction, btn.dataset.file));
  });
}

async function handleDocAction(action, file) {
  try {
    if (action === "view-md") {
      const d = await api(`/api/preview-md?filename=${encodeURIComponent(file)}`);
      showModal(`Markdown — ${file}`, `<pre>${escapeHtml(d.markdown || "(vide)")}</pre>`);
    } else if (action === "view-chunks") {
      const d = await api(`/api/file-chunks?filename=${encodeURIComponent(file)}`);
      const chunks = d.chunks || [];
      if (!chunks.length) {
        showModal(`Chunks — ${file}`, `<div class="empty">Aucun chunk</div>`);
      } else {
        showModal(`${chunks.length} chunks — ${file}`,
          chunks.map(c => `
            <div class="chunk-card">
              <div class="chunk-meta"><span>chunk #${c.chunk_index}</span></div>
              ${c.heading ? `<div class="chunk-heading">${escapeHtml(c.heading)}</div>` : ""}
              <div class="chunk-text">${escapeHtml(c.text)}</div>
            </div>`).join(""));
      }
    } else if (action === "reingest") {
      confirmModal(`Réingérer "${file}" ? Les chunks actuels seront remplacés.`, async () => {
        toast("Réingestion en cours…", "info");
        const r = await api(`/api/reingest?filename=${encodeURIComponent(file)}`, { method: "POST" });
        toast(`Réingéré : ${r.chunks ?? 0} chunks`, "success");
        loadDocuments();
      });
    } else if (action === "delete") {
      confirmModal(`Supprimer "${file}" et tous ses chunks ?`, async () => {
        await api(`/api/file?filename=${encodeURIComponent(file)}`, { method: "DELETE" });
        toast("Document supprimé", "success");
        loadDocuments();
      });
    } else if (action === "ingest-now") {
      toast("Ingestion en cours…", "info");
      const r = await api(`/api/ingest-file?filename=${encodeURIComponent(file)}`, { method: "POST" });
      toast(`Ingéré : ${r.chunks ?? 0} chunks`, "success");
      loadDocuments();
    }
  } catch (e) { toast("Erreur: " + e.message, "error"); }
}

// Drop zone + upload
const dz = $("#dropzone");
dz.addEventListener("click", () => $("#upload-input").click());
dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("drag-over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("drag-over"));
dz.addEventListener("drop", async e => {
  e.preventDefault(); dz.classList.remove("drag-over");
  for (const f of e.dataTransfer.files) await uploadFile(f);
});
$("#upload-input").addEventListener("change", async e => {
  for (const f of e.target.files) await uploadFile(f);
});

async function uploadFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    toast("Seuls les PDFs sont acceptés", "warning"); return;
  }
  toast(`Upload de ${file.name}…`, "info");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const r = await api("/api/upload", { method: "POST", body: fd });
    toast(`${file.name} ingéré (${r.chunks ?? 0} chunks)`, "success");
    loadDocuments();
  } catch (e) { toast("Erreur: " + e.message, "error"); }
}

// ============================================================
// Articles
// ============================================================
async function loadArticles() {
  try {
    const stats = await api("/api/articles/stats");
    $("#art-count").textContent = fmtNum(stats.unique_articles);
    $("#art-sources-count").textContent = (stats.sources || []).length;
    $("#art-chunks").textContent = fmtNum(stats.chunks_total);
    $("#art-words").textContent = fmtNum(stats.total_words);

    const sources = stats.sources || [];
    if (!sources.length) {
      $("#art-sources-table").innerHTML = `<div class="empty">Aucune source. Lance le workflow n8n pour ingérer des articles.</div>`;
    } else {
      $("#art-sources-table").innerHTML = `
        <div class="scroll-x"><table>
          <thead><tr><th>Source</th><th>Articles</th><th></th></tr></thead>
          <tbody>${sources.map(s => `
            <tr>
              <td>${escapeHtml(s.source)}</td>
              <td class="numeric">${s.articles}</td>
              <td class="actions"><button class="btn btn-icon btn-danger" data-art-action="delete-source" data-source="${escapeHtml(s.source)}" title="Vider cette source">${icon("trash","icon-sm")}</button></td>
            </tr>`).join("")}
          </tbody></table></div>`;
    }

    const opts = `<option value="">Toutes</option>` + sources.map(s => `<option>${escapeHtml(s.source)}</option>`).join("");
    $("#art-list-source").innerHTML = opts;

    bindArticleSourceDelete();
  } catch (e) {
    $("#art-sources-table").innerHTML = `<div class="empty">Erreur: ${escapeHtml(e.message)}</div>`;
  }
}

function bindArticleSourceDelete() {
  $$("[data-art-action='delete-source']").forEach(btn => {
    btn.addEventListener("click", () => {
      const src = btn.dataset.source;
      confirmModal(`Supprimer tous les articles de "${src}" ?`, async () => {
        try {
          await api("/api/articles/by-source?source=" + encodeURIComponent(src), { method: "DELETE" });
          toast(`Articles de ${src} supprimés`, "success");
          loadArticles();
        } catch (e) { toast("Erreur: " + e.message, "error"); }
      });
    });
  });
}

$("#art-test-btn").addEventListener("click", async () => {
  const url = $("#art-test-url").value.trim();
  if (!url) { toast("Renseigne une URL", "warning"); return; }
  const btn = $("#art-test-btn");
  btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> Extraction…`;
  try {
    const r = await api("/api/articles/preview-extraction?url=" + encodeURIComponent(url));
    showModal(`Extraction — ${url}`, `
      <dl class="kv" style="margin-bottom:14px">
        <dt>Status</dt><dd>${escapeHtml(r.status)}</dd>
        <dt>Longueur</dt><dd>${fmtNum(r.length)} caractères</dd>
        <dt>Mots</dt><dd>${fmtNum(r.word_count)}</dd>
        <dt>Reading time</dt><dd>${r.reading_time_minutes} min</dd>
        <dt>Langue</dt><dd>${escapeHtml(r.language || "—")}</dd>
        <dt>Auteur</dt><dd>${escapeHtml(r.metadata?.author || "—")}</dd>
        <dt>Titre détecté</dt><dd>${escapeHtml(r.metadata?.title || "—")}</dd>
        <dt>Date</dt><dd>${escapeHtml(r.metadata?.date || "—")}</dd>
      </dl>
      <pre>${escapeHtml(r.markdown || "(vide)")}</pre>`);
  } catch (e) { toast("Erreur: " + e.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "Extraire"; }
});

$("#art-list-load").addEventListener("click", loadArticleList);

async function loadArticleList() {
  const source = $("#art-list-source").value;
  const since = parseInt($("#art-list-since").value) || 0;
  const limit = parseInt($("#art-list-limit").value);
  const params = new URLSearchParams();
  if (source) params.set("source", source);
  if (since > 0) params.set("since_days", since);
  params.set("limit", limit);
  try {
    const data = await api("/api/articles/list?" + params);
    const articles = data.articles || [];
    if (!articles.length) {
      $("#art-list").innerHTML = `<div class="empty">Aucun article</div>`; return;
    }
    $("#art-list").innerHTML = `
      <div class="scroll-x"><table>
        <thead><tr>
          <th>Titre</th><th>Source</th><th>Date</th>
          <th>Words</th><th>Reading</th><th>Lang</th><th>Méthode</th><th></th>
        </tr></thead>
        <tbody>${articles.map(a => `
          <tr>
            <td>
              <a href="${escapeHtml(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.title || "(sans titre)")}</a>
              ${a.summary ? `<div class="meta">${escapeHtml(a.summary.slice(0, 140))}${a.summary.length > 140 ? "…" : ""}</div>` : ""}
            </td>
            <td>${escapeHtml(a.source || "—")}</td>
            <td>${fmtDateOnly(a.published_at)}</td>
            <td class="numeric">${fmtNum(a.word_count)}</td>
            <td class="numeric">${a.reading_time_minutes != null ? a.reading_time_minutes + " min" : "—"}</td>
            <td>${a.language ? `<span class="tag">${escapeHtml(a.language)}</span>` : "—"}</td>
            <td>${a.extraction_method ? `<span class="tag method-${escapeHtml(a.extraction_method)}">${escapeHtml(a.extraction_method)}</span>` : "—"}</td>
            <td class="actions"><div class="row-actions">
              <button class="btn btn-icon" title="Voir contenu extrait" data-art-action="view-extraction" data-url="${escapeHtml(a.url)}">${icon("eye","icon-sm")}</button>
              <button class="btn btn-icon btn-danger" title="Supprimer" data-art-action="delete-url" data-url="${escapeHtml(a.url)}">${icon("trash","icon-sm")}</button>
            </div></td>
          </tr>`).join("")}
        </tbody></table></div>`;
    bindArticleListActions();
  } catch (e) { toast("Erreur: " + e.message, "error"); }
}

function bindArticleListActions() {
  $$("[data-art-action='view-extraction']").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        const d = await api("/api/articles/by-url?url=" + encodeURIComponent(btn.dataset.url));
        showModal(`Extraction — ${escapeHtml(d.title || d.url)}`, `
          <dl class="kv" style="margin-bottom:14px">
            <dt>URL</dt><dd><a href="${escapeHtml(d.url)}" target="_blank" rel="noopener">${escapeHtml(d.url)}</a></dd>
            <dt>Source</dt><dd>${escapeHtml(d.source || "—")}</dd>
            <dt>Auteur</dt><dd>${escapeHtml(d.author || "—")}</dd>
            <dt>Publié</dt><dd>${fmtDate(d.published_at)}</dd>
            <dt>Ingéré</dt><dd>${fmtDate(d.ingested_at)}</dd>
            <dt>Mots</dt><dd>${fmtNum(d.word_count)}</dd>
            <dt>Reading time</dt><dd>${d.reading_time_minutes ?? "—"} min</dd>
            <dt>Langue</dt><dd>${escapeHtml(d.language || "—")}</dd>
            <dt>Méthode</dt><dd>${escapeHtml(d.extraction_method || "—")}</dd>
            <dt>Hash</dt><dd><code>${escapeHtml((d.content_hash || "").slice(0, 16))}…</code></dd>
            <dt>Chunks</dt><dd>${d.n_chunks}</dd>
          </dl>
          <pre>${escapeHtml(d.markdown || "(vide)")}</pre>`);
      } catch (e) { toast("Erreur: " + e.message, "error"); }
    });
  });
  $$("[data-art-action='delete-url']").forEach(btn => {
    btn.addEventListener("click", () => {
      const url = btn.dataset.url;
      confirmModal(`Supprimer cet article ?`, async () => {
        try {
          await api("/api/articles/by-url?url=" + encodeURIComponent(url), { method: "DELETE" });
          toast("Article supprimé", "success");
          loadArticleList(); loadArticles();
        } catch (e) { toast("Erreur: " + e.message, "error"); }
      });
    });
  });
}

$("#art-dup-load").addEventListener("click", async () => {
  try {
    const d = await api("/api/articles/duplicates");
    const groups = d.groups || [];
    if (!groups.length) {
      $("#art-dup").innerHTML = `<div class="empty">Aucun doublon détecté</div>`; return;
    }
    $("#art-dup").innerHTML = groups.map(g => `
      <div class="chunk-card">
        <div class="chunk-meta"><span>hash <code>${escapeHtml(g.content_hash.slice(0, 12))}…</code></span><span>${g.urls.length} URLs</span></div>
        <ul style="margin:6px 0 0;padding-left:18px">${g.urls.map(u => `<li><a href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(u)}</a></li>`).join("")}</ul>
      </div>`).join("");
  } catch (e) { toast("Erreur: " + e.message, "error"); }
});

$("#art-clear-all").addEventListener("click", () => {
  confirmModal("Vider toute la base d'articles ? Action irréversible.", async () => {
    try {
      await api("/api/articles/clear", { method: "DELETE" });
      toast("Base d'articles vidée", "success");
      loadArticles();
    } catch (e) { toast("Erreur: " + e.message, "error"); }
  });
});

$("#art-clear-source").addEventListener("click", () => {
  const src = prompt("Quelle source veux-tu vider ? (ex: 'GitHub Blog')");
  if (!src) return;
  confirmModal(`Supprimer tous les articles de "${src}" ?`, async () => {
    try {
      await api("/api/articles/by-source?source=" + encodeURIComponent(src), { method: "DELETE" });
      toast(`Articles de ${src} supprimés`, "success");
      loadArticles();
    } catch (e) { toast("Erreur: " + e.message, "error"); }
  });
});

// ============================================================
// Search (unified)
// ============================================================
$("#search-k").addEventListener("input", e => $("#search-k-val").textContent = e.target.value);

$$('input[name="target"]').forEach(r => r.addEventListener("change", () => {
  const isArticles = $('input[name="target"]:checked').value === "articles";
  $("#search-source-cell").style.display = isArticles ? "" : "none";
  $("#search-since-cell").style.display = isArticles ? "" : "none";
  if (isArticles) populateSearchSources();
}));

async function populateSearchSources() {
  try {
    const s = await api("/api/articles/sources");
    const opts = `<option value="">Toutes</option>` + (s.sources || []).map(x => `<option>${escapeHtml(x.source)}</option>`).join("");
    $("#search-source").innerHTML = opts;
  } catch (e) { /* silent */ }
}

$("#search-submit").addEventListener("click", async () => {
  const target = $('input[name="target"]:checked').value;
  const question = $("#search-q").value.trim();
  if (!question) { toast("Pose une question", "warning"); return; }
  const top_k = parseInt($("#search-k").value);
  const btn = $("#search-submit");
  btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> Recherche…`;

  try {
    let r;
    if (target === "documents") {
      r = await api("/api/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k }),
      });
    } else {
      const source = $("#search-source").value || null;
      const since_days = parseInt($("#search-since").value) || null;
      r = await api("/api/articles/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k, source, since_days }),
      });
    }
    $("#search-result").style.display = "";
    $("#search-answer").innerHTML = `<pre>${escapeHtml(r.answer || "")}</pre>`;
    const sources = r.sources || [];
    if (!sources.length) {
      $("#search-sources").innerHTML = `<div class="empty">Aucune source pertinente</div>`;
    } else {
      $("#search-sources").innerHTML = sources.map((s, i) => {
        if (target === "articles") {
          return `<div class="source-card">
            <div class="title"><a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${i + 1}. ${escapeHtml(s.title)}</a></div>
            <div class="meta">${escapeHtml(s.source)}${s.published_at ? " · " + fmtDateOnly(s.published_at) : ""} · score ${(s.score || 0).toFixed(3)}</div>
          </div>`;
        }
        return `<div class="source-card">
          <div class="title">${i + 1}. ${escapeHtml(s.source)}</div>
          <div class="meta">chunk #${s.chunk_index} · score ${(s.score || 0).toFixed(3)}${s.heading ? " · " + escapeHtml(s.heading.slice(0, 100)) + (s.heading.length > 100 ? "…" : "") : ""}</div>
        </div>`;
      }).join("");
    }
  } catch (e) { toast("Erreur: " + e.message, "error"); }
  finally { btn.disabled = false; btn.textContent = "Lancer la recherche"; }
});

// ============================================================
// Inspect — chunks browser
// ============================================================
async function loadInspectFilters() {
  const type = $("#insp-type").value;
  try {
    if (type === "documents") {
      const d = await api("/api/files");
      $("#insp-source").innerHTML = `<option value="">Tous</option>` +
        d.processed.map(f => `<option>${escapeHtml(f.name)}</option>`).join("");
    } else {
      const s = await api("/api/articles/sources");
      $("#insp-source").innerHTML = `<option value="">Toutes</option>` +
        (s.sources || []).map(x => `<option>${escapeHtml(x.source)}</option>`).join("");
    }
  } catch (e) { /* silent */ }
}
$("#insp-type").addEventListener("change", loadInspectFilters);

$("#insp-load").addEventListener("click", async () => {
  const type = $("#insp-type").value;
  const src = $("#insp-source").value;
  const limit = parseInt($("#insp-limit").value);
  const filter = $("#insp-filter").value.toLowerCase().trim();
  try {
    let chunks = [];
    if (type === "documents") {
      const url = src
        ? `/api/file-chunks?filename=${encodeURIComponent(src)}&limit=${limit}`
        : `/api/all-chunks?limit=${limit}`;
      const d = await api(url);
      chunks = (d.chunks || []).map(c => ({
        sourceLabel: c.source, idx: c.chunk_index, heading: c.heading, text: c.text,
      }));
    } else {
      const params = new URLSearchParams();
      if (src) params.set("source", src);
      params.set("limit", Math.min(50, limit));
      const list = await api("/api/articles/list?" + params);
      const articles = list.articles || [];
      for (const a of articles) {
        if (chunks.length >= limit) break;
        try {
          const d = await api("/api/articles/by-url?url=" + encodeURIComponent(a.url));
          // Reconstruct from chunks endpoint via scroll: we display raw markdown split rough
          chunks.push({ sourceLabel: a.title, idx: 0, heading: a.source, text: d.markdown });
        } catch (_) { /* skip */ }
      }
    }

    if (filter) chunks = chunks.filter(c => (c.text || "").toLowerCase().includes(filter));

    $("#insp-count").textContent = `${chunks.length} affichés`;
    if (!chunks.length) {
      $("#insp-chunks").innerHTML = `<div class="empty">Aucun chunk</div>`; return;
    }
    $("#insp-chunks").innerHTML = chunks.map(c => `
      <div class="chunk-card">
        <div class="chunk-meta"><span><strong>${escapeHtml(c.sourceLabel || "")}</strong> · #${c.idx ?? 0}</span></div>
        ${c.heading ? `<div class="chunk-heading">${escapeHtml(c.heading)}</div>` : ""}
        <div class="chunk-text">${escapeHtml(c.text)}</div>
      </div>`).join("");
  } catch (e) { toast("Erreur: " + e.message, "error"); }
});

// ============================================================
// System: config + maintenance + logs
// ============================================================
async function loadConfig() {
  try {
    const cfg = await api("/api/config");
    $("#cfg-table tbody").innerHTML = Object.entries(cfg)
      .map(([k, v]) => `<tr><td><code>${escapeHtml(k)}</code></td><td>${escapeHtml(String(v))}</td></tr>`)
      .join("");
  } catch (e) { toast("Erreur: " + e.message, "error"); }
}

$("#sys-clear-docs").addEventListener("click", () => {
  confirmModal("Vider la collection 'documents' (PDFs) ? Les fichiers PDF restent dans processed/.", async () => {
    try {
      await api("/api/clear", { method: "DELETE" });
      toast("Collection vidée", "success");
      loadOverview();
    } catch (e) { toast("Erreur: " + e.message, "error"); }
  });
});

$("#sys-reingest-all").addEventListener("click", () => {
  confirmModal("Réingérer tous les PDFs (inbox + processed) ?", async () => {
    try {
      toast("Réingestion en cours…", "info");
      const r = await api("/api/reingest-all", { method: "POST" });
      toast(`${r.processed} fichiers réingérés`, "success");
      loadOverview(); loadDocuments();
    } catch (e) { toast("Erreur: " + e.message, "error"); }
  });
});

let logsTimer = null;
async function loadLogs() {
  try {
    const lvl = $("#sys-logs-level").value;
    const cnt = $("#sys-logs-count").value;
    const params = new URLSearchParams();
    if (lvl) params.set("level", lvl);
    if (cnt) params.set("count", cnt);
    const d = await api("/api/logs?" + params);
    const lines = d.lines || [];
    $("#sys-logs").innerHTML = lines.map(l => {
      let cls = "info";
      if (/\[ERROR\]/.test(l)) cls = "error";
      else if (/\[WARNING\]/.test(l)) cls = "warning";
      else if (/\[DEBUG\]/.test(l)) cls = "debug";
      return `<div class="log-line ${cls}">${escapeHtml(l)}</div>`;
    }).join("") || `<div class="empty">Pas de logs</div>`;
    $("#sys-logs-status").textContent = `${lines.length} lignes · ${new Date().toLocaleTimeString("fr-FR")}`;
  } catch (e) {
    $("#sys-logs").innerHTML = `<div class="empty">Erreur: ${escapeHtml(e.message)}</div>`;
  }
}
$("#sys-logs-level").addEventListener("change", loadLogs);
$("#sys-logs-count").addEventListener("change", loadLogs);
$("#sys-logs-auto").addEventListener("change", e => {
  if (e.target.checked) {
    if (!logsTimer) logsTimer = setInterval(loadLogs, 5000);
  } else {
    clearInterval(logsTimer); logsTimer = null;
  }
});

// ============================================================
// Bootstrap
// ============================================================
loadOverview();
setInterval(loadOverview, 30000);
if ($("#sys-logs-auto").checked) logsTimer = setInterval(loadLogs, 5000);
