<script lang="ts">
  import type { Article } from '$lib/api';
  import { fmtRelative, fmtNum, truncate } from '$lib/utils';
  import Icon from './Icon.svelte';
  import { goto } from '$app/navigation';

  export let article: Article;
  export let onToggleStar: ((id: string, value: boolean) => void) | undefined = undefined;

  $: unread = article.read_at == null;
  $: title = article.title ?? '(sans titre)';

  function open() {
    goto(`/article/${article.id}`);
  }

  function toggleStar(e: MouseEvent) {
    e.stopPropagation();
    onToggleStar?.(article.id, !article.starred);
  }
</script>

<div
  class="card hover:border-accent/40 cursor-pointer transition-colors"
  on:click={open}
  on:keydown={(e) => e.key === 'Enter' && open()}
  role="button"
  tabindex="0"
>
  <header class="flex items-start justify-between gap-3 mb-2">
    <div class="flex-1 min-w-0">
      <h2 class="font-semibold text-text leading-snug">
        {title}
        {#if unread}<span class="chip-unread ml-2 align-middle">nouveau</span>{/if}
        {#if article.starred}<span class="chip-starred ml-2 align-middle">★</span>{/if}
      </h2>
      <div class="text-xs text-text-mut mt-1 flex gap-2 flex-wrap items-center">
        <span class="font-medium">{article.source}</span>
        <span>·</span>
        <span>{fmtRelative(article.published_at)}</span>
        {#if article.reading_time_minutes}
          <span>·</span>
          <span>{article.reading_time_minutes} min de lecture</span>
        {/if}
        {#if article.word_count}
          <span>·</span>
          <span>{fmtNum(article.word_count)} mots</span>
        {/if}
        {#if article.language}
          <span>·</span>
          <span class="chip">{article.language}</span>
        {/if}
      </div>
    </div>
    <button
      class="btn btn-icon shrink-0"
      class:text-amber-500={article.starred}
      on:click={toggleStar}
      title={article.starred ? 'Retirer des favoris' : 'Mettre en favori'}
    >
      <Icon name={article.starred ? 'star-filled' : 'star'} />
    </button>
  </header>

  {#if article.summary}
    <p class="text-sm text-text-mut leading-relaxed">{truncate(article.summary, 200)}</p>
  {/if}
</div>
