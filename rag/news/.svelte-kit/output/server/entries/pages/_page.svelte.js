import { c as create_ssr_component, f as escape, d as add_attribute, v as validate_component, e as each } from "../../chunks/ssr.js";
import { f as fmtRelative, a as fmtNum, t as truncate } from "../../chunks/utils2.js";
import { I as Icon } from "../../chunks/Icon.js";
import "@sveltejs/kit/internal";
import "../../chunks/exports.js";
import "../../chunks/utils.js";
import "@sveltejs/kit/internal/server";
import "../../chunks/state.svelte.js";
async function req(path, init = {}) {
  const r = await fetch(path, { credentials: "same-origin", ...init });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${r.status}: ${text || r.statusText}`);
  }
  return r.json();
}
async function listArticles(p = {}) {
  const qs = new URLSearchParams();
  if (p.source) qs.set("source", p.source);
  if (p.since_days) qs.set("since_days", String(p.since_days));
  if (p.unread) qs.set("unread", "true");
  if (p.starred) qs.set("starred", "true");
  if (p.q) qs.set("q", p.q);
  if (p.limit) qs.set("limit", String(p.limit));
  if (p.offset) qs.set("offset", String(p.offset));
  if (p.order) qs.set("order", p.order);
  return req(`/api/news/list?${qs}`);
}
async function setStarred(id, value) {
  return req(`/api/news/${id}/star`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value })
  });
}
const ArticleCard = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let unread;
  let title;
  let { article } = $$props;
  let { onToggleStar = void 0 } = $$props;
  if ($$props.article === void 0 && $$bindings.article && article !== void 0) $$bindings.article(article);
  if ($$props.onToggleStar === void 0 && $$bindings.onToggleStar && onToggleStar !== void 0) $$bindings.onToggleStar(onToggleStar);
  unread = article.read_at == null;
  title = article.title ?? "(sans titre)";
  return `<div class="card hover:border-accent/40 cursor-pointer transition-colors" role="button" tabindex="0"><header class="flex items-start justify-between gap-3 mb-2"><div class="flex-1 min-w-0"><h2 class="font-semibold text-text leading-snug">${escape(title)} ${unread ? `<span class="chip-unread ml-2 align-middle" data-svelte-h="svelte-1lr9nsf">nouveau</span>` : ``} ${article.starred ? `<span class="chip-starred ml-2 align-middle" data-svelte-h="svelte-novy1n">★</span>` : ``}</h2> <div class="text-xs text-text-mut mt-1 flex gap-2 flex-wrap items-center"><span class="font-medium">${escape(article.source)}</span> <span data-svelte-h="svelte-5c9bit">·</span> <span>${escape(fmtRelative(article.published_at))}</span> ${article.reading_time_minutes ? `<span data-svelte-h="svelte-5c9bit">·</span> <span>${escape(article.reading_time_minutes)} min de lecture</span>` : ``} ${article.word_count ? `<span data-svelte-h="svelte-5c9bit">·</span> <span>${escape(fmtNum(article.word_count))} mots</span>` : ``} ${article.language ? `<span data-svelte-h="svelte-5c9bit">·</span> <span class="chip">${escape(article.language)}</span>` : ``}</div></div> <button class="${["btn btn-icon shrink-0", article.starred ? "text-amber-500" : ""].join(" ").trim()}"${add_attribute(
    "title",
    article.starred ? "Retirer des favoris" : "Mettre en favori",
    0
  )}>${validate_component(Icon, "Icon").$$render(
    $$result,
    {
      name: article.starred ? "star-filled" : "star"
    },
    {},
    {}
  )}</button></header> ${article.summary ? `<p class="text-sm text-text-mut leading-relaxed">${escape(truncate(article.summary, 200))}</p>` : ``}</div>`;
});
const FilterSidebar = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let { q = "" } = $$props;
  let { source = "" } = $$props;
  let { sinceDays = 0 } = $$props;
  let { status = "all" } = $$props;
  let { sourcesList = [] } = $$props;
  const periods = [
    { label: "24h", value: 1 },
    { label: "7j", value: 7 },
    { label: "30j", value: 30 },
    { label: "Tous", value: 0 }
  ];
  if ($$props.q === void 0 && $$bindings.q && q !== void 0) $$bindings.q(q);
  if ($$props.source === void 0 && $$bindings.source && source !== void 0) $$bindings.source(source);
  if ($$props.sinceDays === void 0 && $$bindings.sinceDays && sinceDays !== void 0) $$bindings.sinceDays(sinceDays);
  if ($$props.status === void 0 && $$bindings.status && status !== void 0) $$bindings.status(status);
  if ($$props.sourcesList === void 0 && $$bindings.sourcesList && sourcesList !== void 0) $$bindings.sourcesList(sourcesList);
  return `<aside class="w-64 shrink-0 space-y-5"><div><label class="block text-xs font-semibold text-text-mut uppercase tracking-wider mb-2" for="filter-q" data-svelte-h="svelte-1a2y3z4">Recherche</label> <div class="relative"><span class="absolute left-2.5 top-2.5 text-text-mut">${validate_component(Icon, "Icon").$$render($$result, { name: "search", size: 14 }, {}, {})}</span> <input id="filter-q" type="text" placeholder="Filtrer par titre…" class="input pl-8"${add_attribute("value", q, 0)}></div></div> <div><div class="text-xs font-semibold text-text-mut uppercase tracking-wider mb-2" data-svelte-h="svelte-1evmyjf">Statut</div> <div class="flex flex-col gap-1">${each(
    [
      { v: "all", l: "Tous" },
      { v: "unread", l: "Non lus" },
      { v: "starred", l: "Favoris" }
    ],
    (opt) => {
      return `<label class="flex items-center gap-2 text-sm cursor-pointer"><input type="radio"${add_attribute("value", opt.v, 0)} class="accent-accent"${opt.v === status ? add_attribute("checked", true, 1) : ""}> <span class="text-text">${escape(opt.l)}</span> </label>`;
    }
  )}</div></div> <div><div class="text-xs font-semibold text-text-mut uppercase tracking-wider mb-2" data-svelte-h="svelte-12w82zw">Période</div> <div class="flex flex-wrap gap-1">${each(periods, (p) => {
    return `<button class="${[
      "btn",
      (sinceDays === p.value ? "bg-accent-bg" : "") + " " + (sinceDays === p.value ? "border-accent" : "") + " " + (sinceDays === p.value ? "text-accent" : "")
    ].join(" ").trim()}">${escape(p.label)}</button>`;
  })}</div></div> <div><div class="text-xs font-semibold text-text-mut uppercase tracking-wider mb-2" data-svelte-h="svelte-r1s5m5">Source</div> <div class="space-y-0.5 max-h-72 overflow-y-auto"><label class="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-bg-mut cursor-pointer text-sm"><span class="flex items-center gap-2"><input type="radio" value="" class="accent-accent"${"" === source ? add_attribute("checked", true, 1) : ""}> <span data-svelte-h="svelte-n6kj8m">Toutes</span></span></label> ${each(sourcesList, (s) => {
    return `<label class="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-bg-mut cursor-pointer text-sm"><span class="flex items-center gap-2 min-w-0"><input type="radio"${add_attribute("value", s.source, 0)} class="accent-accent"${s.source === source ? add_attribute("checked", true, 1) : ""}> <span class="truncate">${escape(s.source)}</span></span> <span class="text-xs text-text-mut tabular-nums">${escape(s.unread > 0 ? `${s.unread}/${s.total}` : s.total)}</span> </label>`;
  })}</div></div></aside>`;
});
let limit = 30;
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let articles = [];
  let total = 0;
  let loading = true;
  let error = "";
  let q = "";
  let source = "";
  let sinceDays = 0;
  let status = "all";
  let sourcesList = [];
  let offset = 0;
  async function load(reset = true) {
    if (reset) offset = 0;
    loading = true;
    error = "";
    try {
      const r = await listArticles({
        source: source || void 0,
        since_days: sinceDays || void 0,
        unread: status === "unread",
        starred: status === "starred",
        q: q || void 0,
        limit,
        offset,
        order: "published_at_desc"
      });
      articles = reset ? r.articles : [...articles, ...r.articles];
      total = r.total;
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
  async function toggleStar(id, value) {
    try {
      const updated = await setStarred(id, value);
      articles = articles.map((a) => a.id === id ? updated : a);
    } catch (e) {
      error = e.message;
    }
  }
  let $$settled;
  let $$rendered;
  let previous_head = $$result.head;
  do {
    $$settled = true;
    $$result.head = previous_head;
    {
      load(true);
    }
    $$rendered = `<div class="flex gap-6">${validate_component(FilterSidebar, "FilterSidebar").$$render(
      $$result,
      {
        sourcesList,
        q,
        source,
        sinceDays,
        status
      },
      {
        q: ($$value) => {
          q = $$value;
          $$settled = false;
        },
        source: ($$value) => {
          source = $$value;
          $$settled = false;
        },
        sinceDays: ($$value) => {
          sinceDays = $$value;
          $$settled = false;
        },
        status: ($$value) => {
          status = $$value;
          $$settled = false;
        }
      },
      {}
    )} <section class="flex-1 min-w-0 space-y-4"><div class="flex items-center justify-between"><div class="text-sm text-text-mut">${loading && articles.length === 0 ? `Chargement…` : `<span class="font-medium text-text">${escape(fmtNum(total))}</span> article${escape(total > 1 ? "s" : "")} ${``}`}</div> <div class="flex gap-2"><button class="btn">${validate_component(Icon, "Icon").$$render($$result, { name: "refresh", size: 14 }, {}, {})} Rafraîchir</button> ${``}</div></div> ${error ? `<div class="card border-danger bg-danger-bg text-danger">${escape(error)}</div>` : ``} ${articles.length === 0 && !loading ? `<div class="card text-center text-text-mut" data-svelte-h="svelte-1nlv1ng">Aucun article. Lance le workflow n8n pour ingérer du contenu.</div>` : `<div class="space-y-3">${each(articles, (a) => {
      return `${validate_component(ArticleCard, "ArticleCard").$$render($$result, { article: a, onToggleStar: toggleStar }, {}, {})}`;
    })}</div> ${articles.length < total ? `<div class="text-center pt-4"><button class="btn" ${loading ? "disabled" : ""}>${escape(loading ? "Chargement…" : `Charger plus (${articles.length} / ${total})`)}</button></div>` : ``}`}</section></div>`;
  } while (!$$settled);
  return $$rendered;
});
export {
  Page as default
};
