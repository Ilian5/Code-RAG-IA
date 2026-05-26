import { c as create_ssr_component, b as subscribe, e as each, d as add_attribute, v as validate_component, f as escape } from "../../chunks/ssr.js";
import { p as page } from "../../chunks/stores.js";
import { I as Icon } from "../../chunks/Icon.js";
const Layout = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let currentPath;
  let $page, $$unsubscribe_page;
  $$unsubscribe_page = subscribe(page, (value) => $page = value);
  const tabs = [
    {
      href: "/",
      label: "Articles",
      icon: "list"
    },
    {
      href: "/chat",
      label: "Chat",
      icon: "bot"
    },
    {
      href: "/stats",
      label: "Stats",
      icon: "stats"
    }
  ];
  currentPath = $page.url.pathname;
  $$unsubscribe_page();
  return `<div class="min-h-screen flex flex-col"><header class="border-b border-border bg-bg sticky top-0 z-30"><div class="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between"><a href="/" class="font-semibold text-base tracking-tight" data-svelte-h="svelte-h9af9c">Tech <span class="text-text-mut font-normal">News</span></a> <nav class="flex gap-1">${each(tabs, (t) => {
    return `<a${add_attribute("href", t.href, 0)} class="${[
      "px-3 py-1.5 rounded-md text-sm flex items-center gap-2 transition-colors",
      (currentPath === t.href || t.href !== "/" && currentPath.startsWith(t.href) ? "bg-bg-mut" : "") + " " + (currentPath === t.href || t.href !== "/" && currentPath.startsWith(t.href) ? "text-text" : "") + " " + (!(currentPath === t.href || t.href !== "/" && currentPath.startsWith(t.href)) ? "text-text-mut" : "")
    ].join(" ").trim()}">${validate_component(Icon, "Icon").$$render($$result, { name: t.icon, size: 14 }, {}, {})} ${escape(t.label)} </a>`;
  })}</nav></div></header> <main class="flex-1 max-w-7xl w-full mx-auto px-6 py-6">${slots.default ? slots.default({}) : ``}</main> <footer class="border-t border-border py-4 text-xs text-text-mut text-center" data-svelte-h="svelte-1ir0v32">Ingestion automatique via n8n. Index sémantique : Qdrant + Ollama (Llama 3.2, nomic-embed-text).</footer></div>`;
});
export {
  Layout as default
};
