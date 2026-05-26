<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';
  import type { Stats, SourceCount } from '$lib/api';
  import { fmtNum, fmtDate } from '$lib/utils';

  let stats: Stats | null = null;
  let sources: SourceCount[] = [];
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      const [s, src] = await Promise.all([api.stats(), api.sources()]);
      stats = s;
      sources = src.sources;
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  });

  $: maxSourceTotal = Math.max(1, ...sources.map(s => s.total));
  $: maxDaily = stats ? Math.max(1, ...stats.daily_ingestion_30d.map(d => d.count)) : 1;
</script>

<div class="space-y-6">
  <header>
    <h1 class="text-xl font-semibold mb-1">Statistiques</h1>
    <p class="text-sm text-text-mut">Vue d'ensemble du contenu indexé.</p>
  </header>

  {#if loading}
    <div class="text-text-mut text-sm">Chargement…</div>
  {:else if error}
    <div class="card border-danger bg-danger-bg text-danger">{error}</div>
  {:else if stats}
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
      <div class="card">
        <div class="text-xs text-text-mut uppercase tracking-wider mb-1">Total</div>
        <div class="text-2xl font-semibold">{fmtNum(stats.total)}</div>
      </div>
      <div class="card">
        <div class="text-xs text-text-mut uppercase tracking-wider mb-1">Non lus</div>
        <div class="text-2xl font-semibold text-accent">{fmtNum(stats.unread)}</div>
      </div>
      <div class="card">
        <div class="text-xs text-text-mut uppercase tracking-wider mb-1">Favoris</div>
        <div class="text-2xl font-semibold text-amber-500">{fmtNum(stats.starred)}</div>
      </div>
      <div class="card">
        <div class="text-xs text-text-mut uppercase tracking-wider mb-1">Mots indexés</div>
        <div class="text-2xl font-semibold">{fmtNum(stats.total_words)}</div>
      </div>
    </div>

    <div class="card">
      <h2 class="font-semibold text-base mb-4">Sources</h2>
      <div class="space-y-1.5">
        {#each sources as s}
          <div class="grid grid-cols-[1fr_auto] gap-3 items-center text-sm">
            <div class="min-w-0">
              <div class="flex justify-between mb-0.5">
                <span class="truncate font-medium">{s.source}</span>
                <span class="text-text-mut tabular-nums">
                  {s.unread > 0 ? `${s.unread} non lus / ` : ''}{s.total}
                </span>
              </div>
              <div class="h-1.5 bg-bg-mut rounded overflow-hidden">
                <div class="h-full bg-accent" style="width: {(s.total / maxSourceTotal) * 100}%"></div>
              </div>
            </div>
            <div class="text-xs text-text-mut whitespace-nowrap">
              {s.last_published ? fmtDate(s.last_published) : '—'}
            </div>
          </div>
        {/each}
      </div>
    </div>

    <div class="card">
      <h2 class="font-semibold text-base mb-4">Ingestion des 30 derniers jours</h2>
      <div class="flex items-end gap-1 h-32">
        {#each stats.daily_ingestion_30d as d}
          <div class="flex-1 flex flex-col items-center justify-end" title="{d.day}: {d.count} articles">
            <div class="w-full bg-accent rounded-t" style="height: {(d.count / maxDaily) * 100}%; min-height: 2px;"></div>
          </div>
        {/each}
      </div>
      <div class="flex justify-between text-xs text-text-mut mt-2">
        <span>{stats.daily_ingestion_30d[0]?.day ?? ''}</span>
        <span>{stats.daily_ingestion_30d[stats.daily_ingestion_30d.length - 1]?.day ?? ''}</span>
      </div>
    </div>

    <div class="card">
      <h2 class="font-semibold text-base mb-4">Langues</h2>
      <div class="flex flex-wrap gap-2">
        {#each Object.entries(stats.languages) as [lang, n]}
          <div class="chip">
            <span class="font-medium">{lang}</span>
            <span class="ml-2 text-text-mut">{n}</span>
          </div>
        {/each}
      </div>
    </div>
  {/if}
</div>
