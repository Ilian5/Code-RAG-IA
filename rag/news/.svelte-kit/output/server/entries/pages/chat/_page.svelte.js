import { c as create_ssr_component, d as add_attribute, e as each, f as escape, v as validate_component } from "../../../chunks/ssr.js";
import { I as Icon } from "../../../chunks/Icon.js";
import { b as fmtDate } from "../../../chunks/utils2.js";
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let messages = [];
  let input = "";
  let unreadOnly = false;
  let topK = 5;
  return `<div class="max-w-4xl mx-auto"><header class="mb-6" data-svelte-h="svelte-64wu0t"><h1 class="text-xl font-semibold mb-1">Chat sur les articles</h1> <p class="text-sm text-text-mut">Pose une question — la réponse synthétise les articles indexés via RAG.</p></header> <div class="card mb-4"><div class="flex flex-wrap gap-4 text-sm"><label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" class="accent-accent"${add_attribute("checked", unreadOnly, 1)}> <span data-svelte-h="svelte-1darit6">Uniquement non lus</span></label> <label class="flex items-center gap-2"><span class="text-text-mut" data-svelte-h="svelte-66s01p">Depuis :</span> <select class="input w-auto py-1"><option${add_attribute("value", 0, 0)} data-svelte-h="svelte-13z5zsz">tous</option><option${add_attribute("value", 1, 0)} data-svelte-h="svelte-1vxsp3x">24h</option><option${add_attribute("value", 7, 0)} data-svelte-h="svelte-1oaoioi">7j</option><option${add_attribute("value", 30, 0)} data-svelte-h="svelte-1l4486a">30j</option></select></label> <label class="flex items-center gap-2"><span class="text-text-mut" data-svelte-h="svelte-xx15hc">Top-K :</span> <input type="number" min="1" max="15" class="input w-16 py-1"${add_attribute("value", topK, 0)}></label></div></div> <div class="space-y-4 mb-6">${each(messages, (m, i) => {
    return `${m.role === "user" ? `<div class="flex justify-end"><div class="bg-accent-bg text-text px-4 py-2.5 rounded-lg max-w-2xl whitespace-pre-wrap text-sm">${escape(m.text)}</div> </div>` : `${m.role === "pending" ? `<div class="flex items-center gap-2 text-sm text-text-mut">${validate_component(Icon, "Icon").$$render($$result, { name: "loader", size: 14 }, {}, {})} <span data-svelte-h="svelte-fgoj77">Recherche dans les articles… (5-30s)</span> </div>` : `<div class="space-y-2"><div class="bg-bg-mut border border-border px-4 py-3 rounded-lg whitespace-pre-wrap text-sm leading-relaxed">${escape(m.text)}</div> ${m.sources?.length ? `<div class="space-y-1"><div class="text-xs text-text-mut uppercase tracking-wider mb-1" data-svelte-h="svelte-9gw4fe">Sources</div> ${each(m.sources, (s) => {
      return `<a${add_attribute("href", s.id ? `/article/${s.id}` : s.url, 0)}${add_attribute("target", s.id ? "_self" : "_blank", 0)} rel="noopener" class="block card hover:border-accent text-sm"><div class="font-medium text-text">${escape(s.title)}</div> <div class="text-xs text-text-mut mt-0.5">${escape(s.source)} ${s.published_at ? `· ${escape(fmtDate(s.published_at))}` : ``}
                    · score ${escape((s.score ?? 0).toFixed(3))}</div> </a>`;
    })} </div>` : ``} </div>`}`}`;
  })} ${``} ${messages.length === 0 ? `<div class="text-text-mut text-sm" data-svelte-h="svelte-69g8ka">Exemples : « Quoi de neuf sur les LLMs locaux ? », « Résume les dernières news Cloudflare », « Articles sur Rust cette semaine ? »</div>` : ``}</div> <div class="sticky bottom-4 bg-bg border border-border rounded-lg shadow-soft p-2 flex items-end gap-2"><textarea placeholder="Pose une question… (Ctrl+Entrée pour envoyer)" rows="2" class="input border-0 focus:ring-0 resize-none">${escape("")}</textarea> <button class="btn-primary" ${!input.trim() ? "disabled" : ""}>${validate_component(Icon, "Icon").$$render($$result, { name: "send", size: 14 }, {}, {})}
      Envoyer</button></div></div>`;
});
export {
  Page as default
};
