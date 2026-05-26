<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import * as api from '$lib/api';
  import type { ArticleWithMarkdown } from '$lib/api';
  import Icon from '$lib/components/Icon.svelte';
  import { fmtDateTime, fmtNum } from '$lib/utils';

  let article: ArticleWithMarkdown | null = null;
  let loading = true;
  let error = '';

  $: id = $page.params.id;

  onMount(async () => {
    try {
      article = await api.getArticle(id);
      // Auto-mark as read after a small delay if it wasn't already.
      if (article && article.read_at == null) {
        setTimeout(async () => {
          if (article && article.read_at == null) {
            const updated = await api.setRead(article.id, true);
            article = { ...article, ...updated };
          }
        }, 2000);
      }
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  });

  async function toggleStar() {
    if (!article) return;
    const updated = await api.setStarred(article.id, !article.starred);
    article = { ...article, ...updated };
  }

  async function toggleRead() {
    if (!article) return;
    const newValue = article.read_at == null;
    const updated = await api.setRead(article.id, newValue);
    article = { ...article, ...updated };
  }

  // Minimal markdown → HTML renderer. Replaces headers, lists, code, paragraphs.
  function renderMarkdown(md: string): string {
    if (!md) return '';
    const escape = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string));
    let html = escape(md);
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    html = html.replace(/\[Section: (.+?)\]/g, '<div class="text-xs uppercase tracking-wider text-text-mut my-4 border-b border-border pb-1">$1</div>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // Paragraphs (split on blank lines)
    const blocks = html.split(/\n\n+/).map(b => {
      const t = b.trim();
      if (!t) return '';
      if (t.startsWith('<h') || t.startsWith('<div')) return t;
      return `<p>${t.replace(/\n/g, '<br/>')}</p>`;
    });
    return blocks.join('\n');
  }
</script>

{#if loading}
  <div class="text-text-mut text-sm">Chargement…</div>
{:else if error}
  <div class="card border-danger bg-danger-bg text-danger">{error}</div>
{:else if article}
  <div class="max-w-3xl mx-auto">
    <div class="flex items-center gap-3 mb-6">
      <button class="btn btn-icon" on:click={() => goto('/')}>
        <Icon name="chevron" size={14} strokeWidth={2}/>
      </button>
      <div class="text-xs text-text-mut">Retour</div>
    </div>

    <header class="mb-6 pb-6 border-b border-border">
      <h1 class="text-2xl font-semibold text-text leading-tight mb-3">
        {article.title ?? '(sans titre)'}
      </h1>
      <div class="flex flex-wrap gap-2 text-sm text-text-mut">
        <span class="font-medium text-text">{article.source}</span>
        {#if article.author}<span>· {article.author}</span>{/if}
        {#if article.published_at}<span>· {fmtDateTime(article.published_at)}</span>{/if}
        {#if article.reading_time_minutes}<span>· {article.reading_time_minutes} min de lecture</span>{/if}
        {#if article.word_count}<span>· {fmtNum(article.word_count)} mots</span>{/if}
        {#if article.language}<span class="chip">{article.language}</span>{/if}
      </div>
      <div class="flex gap-2 mt-4">
        <button class="btn" on:click={toggleRead}>
          <Icon name="check" size={14}/>
          {article.read_at == null ? 'Marquer comme lu' : 'Marquer comme non lu'}
        </button>
        <button class="btn" class:text-amber-500={article.starred} on:click={toggleStar}>
          <Icon name={article.starred ? 'star-filled' : 'star'} size={14}/>
          {article.starred ? 'Favori' : 'Ajouter aux favoris'}
        </button>
        <a class="btn" href={article.url} target="_blank" rel="noopener">
          <Icon name="external" size={14}/>
          Lien original
        </a>
      </div>
    </header>

    <article class="prose prose-sm max-w-none prose-headings:font-semibold prose-headings:tracking-tight prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-p:leading-relaxed prose-p:text-text prose-code:bg-bg-mut prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-text prose-code:font-mono">
      {@html renderMarkdown(article.markdown)}
    </article>
  </div>
{/if}
