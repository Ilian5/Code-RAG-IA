<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import Icon from '$lib/components/Icon.svelte';

  const tabs = [
    { href: '/',      label: 'Articles', icon: 'list' },
    { href: '/chat',  label: 'Chat',     icon: 'bot' },
    { href: '/stats', label: 'Stats',    icon: 'stats' },
  ];

  $: currentPath = $page.url.pathname;
</script>

<div class="min-h-screen flex flex-col">
  <header class="border-b border-border bg-bg sticky top-0 z-30">
    <div class="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
      <a href="/" class="font-semibold text-base tracking-tight">
        Tech <span class="text-text-mut font-normal">News</span>
      </a>
      <nav class="flex gap-1">
        {#each tabs as t}
          <a
            href={t.href}
            class="px-3 py-1.5 rounded-md text-sm flex items-center gap-2 transition-colors"
            class:bg-bg-mut={currentPath === t.href || (t.href !== '/' && currentPath.startsWith(t.href))}
            class:text-text={currentPath === t.href || (t.href !== '/' && currentPath.startsWith(t.href))}
            class:text-text-mut={!(currentPath === t.href || (t.href !== '/' && currentPath.startsWith(t.href)))}
          >
            <Icon name={t.icon} size={14}/>
            {t.label}
          </a>
        {/each}
      </nav>
    </div>
  </header>

  <main class="flex-1 max-w-7xl w-full mx-auto px-6 py-6">
    <slot/>
  </main>

  <footer class="border-t border-border py-4 text-xs text-text-mut text-center">
    Ingestion automatique via n8n. Index sémantique : Qdrant + Ollama (Llama 3.2, nomic-embed-text).
  </footer>
</div>
