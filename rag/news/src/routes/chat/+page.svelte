<script lang="ts">
  import * as api from '$lib/api';
  import type { ChatSource } from '$lib/api';
  import Icon from '$lib/components/Icon.svelte';
  import { fmtDate } from '$lib/utils';

  type Message =
    | { role: 'user'; text: string }
    | { role: 'assistant'; text: string; sources: ChatSource[] }
    | { role: 'pending' };

  let messages: Message[] = [];
  let input = '';
  let pending = false;
  let unreadOnly = false;
  let sinceDays = 0;
  let topK = 5;
  let error = '';

  async function send() {
    const q = input.trim();
    if (!q || pending) return;
    input = '';
    error = '';
    messages = [...messages, { role: 'user', text: q }, { role: 'pending' }];
    pending = true;
    try {
      const r = await api.chat(q, {
        top_k: topK,
        unread_only: unreadOnly,
        since_days: sinceDays || undefined,
      });
      messages = messages.slice(0, -1).concat({ role: 'assistant', text: r.answer, sources: r.sources });
    } catch (e: any) {
      messages = messages.slice(0, -1);
      error = e.message;
    } finally {
      pending = false;
    }
  }

  function handleKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      send();
    }
  }
</script>

<div class="max-w-4xl mx-auto">
  <header class="mb-6">
    <h1 class="text-xl font-semibold mb-1">Chat sur les articles</h1>
    <p class="text-sm text-text-mut">Pose une question — la réponse synthétise les articles indexés via RAG.</p>
  </header>

  <div class="card mb-4">
    <div class="flex flex-wrap gap-4 text-sm">
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" bind:checked={unreadOnly} class="accent-accent"/>
        <span>Uniquement non lus</span>
      </label>
      <label class="flex items-center gap-2">
        <span class="text-text-mut">Depuis :</span>
        <select bind:value={sinceDays} class="input w-auto py-1">
          <option value={0}>tous</option>
          <option value={1}>24h</option>
          <option value={7}>7j</option>
          <option value={30}>30j</option>
        </select>
      </label>
      <label class="flex items-center gap-2">
        <span class="text-text-mut">Top-K :</span>
        <input type="number" min="1" max="15" bind:value={topK} class="input w-16 py-1"/>
      </label>
    </div>
  </div>

  <div class="space-y-4 mb-6">
    {#each messages as m, i (i)}
      {#if m.role === 'user'}
        <div class="flex justify-end">
          <div class="bg-accent-bg text-text px-4 py-2.5 rounded-lg max-w-2xl whitespace-pre-wrap text-sm">{m.text}</div>
        </div>
      {:else if m.role === 'pending'}
        <div class="flex items-center gap-2 text-sm text-text-mut">
          <Icon name="loader" size={14}/>
          <span>Recherche dans les articles… (5-30s)</span>
        </div>
      {:else}
        <div class="space-y-2">
          <div class="bg-bg-mut border border-border px-4 py-3 rounded-lg whitespace-pre-wrap text-sm leading-relaxed">{m.text}</div>
          {#if m.sources?.length}
            <div class="space-y-1">
              <div class="text-xs text-text-mut uppercase tracking-wider mb-1">Sources</div>
              {#each m.sources as s}
                <a
                  href={s.id ? `/article/${s.id}` : s.url}
                  target={s.id ? '_self' : '_blank'}
                  rel="noopener"
                  class="block card hover:border-accent text-sm"
                >
                  <div class="font-medium text-text">{s.title}</div>
                  <div class="text-xs text-text-mut mt-0.5">
                    {s.source}
                    {#if s.published_at} · {fmtDate(s.published_at)}{/if}
                    · score {(s.score ?? 0).toFixed(3)}
                  </div>
                </a>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    {/each}

    {#if error}
      <div class="card border-danger bg-danger-bg text-danger text-sm">{error}</div>
    {/if}

    {#if messages.length === 0}
      <div class="text-text-mut text-sm">
        Exemples : « Quoi de neuf sur les LLMs locaux ? », « Résume les dernières news Cloudflare », « Articles sur Rust cette semaine ? »
      </div>
    {/if}
  </div>

  <div class="sticky bottom-4 bg-bg border border-border rounded-lg shadow-soft p-2 flex items-end gap-2">
    <textarea
      bind:value={input}
      on:keydown={handleKey}
      placeholder="Pose une question… (Ctrl+Entrée pour envoyer)"
      rows="2"
      class="input border-0 focus:ring-0 resize-none"
    />
    <button class="btn-primary" on:click={send} disabled={pending || !input.trim()}>
      <Icon name="send" size={14}/>
      Envoyer
    </button>
  </div>
</div>
