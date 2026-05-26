<script lang="ts">
  import { onMount } from 'svelte';
  import * as api from '$lib/api';
  import type { Article, SourceCount } from '$lib/api';
  import ArticleCard from '$lib/components/ArticleCard.svelte';
  import FilterSidebar from '$lib/components/FilterSidebar.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { fmtNum } from '$lib/utils';

  let articles: Article[] = [];
  let total = 0;
  let loading = true;
  let error = '';

  let q = '';
  let source = '';
  let sinceDays = 0;
  let status: 'all' | 'unread' | 'starred' = 'all';

  let sourcesList: SourceCount[] = [];
  let totalUnread = 0;

  let limit = 30;
  let offset = 0;

  async function loadSources() {
    try {
      const r = await api.sources();
      sourcesList = r.sources;
      totalUnread = r.sources.reduce((sum, s) => sum + s.unread, 0);
    } catch (e: any) { console.error(e); }
  }

  async function load(reset = true) {
    if (reset) offset = 0;
    loading = true;
    error = '';
    try {
      const r = await api.listArticles({
        source: source || undefined,
        since_days: sinceDays || undefined,
        unread: status === 'unread',
        starred: status === 'starred',
        q: q || undefined,
        limit,
        offset,
        order: 'published_at_desc',
      });
      articles = reset ? r.articles : [...articles, ...r.articles];
      total = r.total;
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  $: (q, source, sinceDays, status), load(true);

  onMount(async () => {
    await loadSources();
  });

  async function loadMore() {
    offset += limit;
    await load(false);
  }

  async function toggleStar(id: string, value: boolean) {
    try {
      const updated = await api.setStarred(id, value);
      articles = articles.map(a => a.id === id ? updated : a);
    } catch (e: any) { error = e.message; }
  }

  async function markAllRead() {
    if (!confirm(source ? `Marquer tous les articles de "${source}" comme lus ?` : 'Marquer TOUS les articles comme lus ?')) return;
    await api.markAllRead(source || undefined);
    await Promise.all([load(true), loadSources()]);
  }
</script>

<div class="flex gap-6">
  <FilterSidebar bind:q bind:source bind:sinceDays bind:status {sourcesList}/>

  <section class="flex-1 min-w-0 space-y-4">
    <div class="flex items-center justify-between">
      <div class="text-sm text-text-mut">
        {#if loading && articles.length === 0}
          Chargement…
        {:else}
          <span class="font-medium text-text">{fmtNum(total)}</span> article{total > 1 ? 's' : ''}
          {#if totalUnread > 0}· <span class="text-accent">{totalUnread} non lus</span>{/if}
        {/if}
      </div>
      <div class="flex gap-2">
        <button class="btn" on:click={() => { loadSources(); load(true); }}>
          <Icon name="refresh" size={14}/> Rafraîchir
        </button>
        {#if totalUnread > 0}
          <button class="btn" on:click={markAllRead}>
            <Icon name="check" size={14}/>
            {source ? `Tout lire (${source})` : 'Tout marquer lu'}
          </button>
        {/if}
      </div>
    </div>

    {#if error}
      <div class="card border-danger bg-danger-bg text-danger">{error}</div>
    {/if}

    {#if articles.length === 0 && !loading}
      <div class="card text-center text-text-mut">Aucun article. Lance le workflow n8n pour ingérer du contenu.</div>
    {:else}
      <div class="space-y-3">
        {#each articles as a (a.id)}
          <ArticleCard article={a} onToggleStar={toggleStar}/>
        {/each}
      </div>

      {#if articles.length < total}
        <div class="text-center pt-4">
          <button class="btn" on:click={loadMore} disabled={loading}>
            {loading ? 'Chargement…' : `Charger plus (${articles.length} / ${total})`}
          </button>
        </div>
      {/if}
    {/if}
  </section>
</div>
