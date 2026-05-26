<script lang="ts">
  import type { SourceCount } from '$lib/api';
  import Icon from './Icon.svelte';

  export let q: string = '';
  export let source: string = '';
  export let sinceDays: number = 0;
  export let status: 'all' | 'unread' | 'starred' = 'all';
  export let sourcesList: SourceCount[] = [];

  const periods = [
    { label: '24h', value: 1 },
    { label: '7j', value: 7 },
    { label: '30j', value: 30 },
    { label: 'Tous', value: 0 },
  ];
</script>

<aside class="w-64 shrink-0 space-y-5">
  <div>
    <label class="block text-xs font-semibold text-text-mut uppercase tracking-wider mb-2" for="filter-q">Recherche</label>
    <div class="relative">
      <span class="absolute left-2.5 top-2.5 text-text-mut"><Icon name="search" size={14}/></span>
      <input id="filter-q" type="text" bind:value={q} placeholder="Filtrer par titre…" class="input pl-8" />
    </div>
  </div>

  <div>
    <div class="text-xs font-semibold text-text-mut uppercase tracking-wider mb-2">Statut</div>
    <div class="flex flex-col gap-1">
      {#each [{v:'all',l:'Tous'},{v:'unread',l:'Non lus'},{v:'starred',l:'Favoris'}] as opt}
        <label class="flex items-center gap-2 text-sm cursor-pointer">
          <input type="radio" bind:group={status} value={opt.v} class="accent-accent"/>
          <span class="text-text">{opt.l}</span>
        </label>
      {/each}
    </div>
  </div>

  <div>
    <div class="text-xs font-semibold text-text-mut uppercase tracking-wider mb-2">Période</div>
    <div class="flex flex-wrap gap-1">
      {#each periods as p}
        <button
          class="btn"
          class:bg-accent-bg={sinceDays === p.value}
          class:border-accent={sinceDays === p.value}
          class:text-accent={sinceDays === p.value}
          on:click={() => sinceDays = p.value}
        >{p.label}</button>
      {/each}
    </div>
  </div>

  <div>
    <div class="text-xs font-semibold text-text-mut uppercase tracking-wider mb-2">Source</div>
    <div class="space-y-0.5 max-h-72 overflow-y-auto">
      <label class="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-bg-mut cursor-pointer text-sm">
        <span class="flex items-center gap-2">
          <input type="radio" bind:group={source} value="" class="accent-accent"/>
          <span>Toutes</span>
        </span>
      </label>
      {#each sourcesList as s}
        <label class="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-bg-mut cursor-pointer text-sm">
          <span class="flex items-center gap-2 min-w-0">
            <input type="radio" bind:group={source} value={s.source} class="accent-accent"/>
            <span class="truncate">{s.source}</span>
          </span>
          <span class="text-xs text-text-mut tabular-nums">
            {s.unread > 0 ? `${s.unread}/${s.total}` : s.total}
          </span>
        </label>
      {/each}
    </div>
  </div>
</aside>
