/** Typed API client for the news backend. All endpoints are served under /api/. */

export type Article = {
  id: string;
  url: string;
  title: string | null;
  source: string;
  author: string | null;
  published_at: string | null;
  ingested_at: string;
  extracted_at: string | null;
  content_hash: string | null;
  word_count: number | null;
  reading_time_minutes: number | null;
  language: string | null;
  extraction_method: string | null;
  summary: string | null;
  rss_categories: string[] | null;
  n_chunks: number | null;
  read_at: string | null;
  starred: boolean;
};

export type ArticleWithMarkdown = Article & { markdown: string };

export type ListParams = {
  source?: string;
  since_days?: number;
  unread?: boolean;
  starred?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
  order?: 'published_at_desc' | 'published_at_asc' | 'ingested_at_desc';
};

export type SourceCount = {
  source: string;
  total: number;
  unread: number;
  last_published: string | null;
};

export type Stats = {
  total: number;
  unread: number;
  starred: number;
  total_words: number;
  languages: Record<string, number>;
  daily_ingestion_30d: { day: string; count: number }[];
};

export type ChatSource = {
  id: string | null;
  title: string;
  source: string;
  url: string;
  published_at: string;
  score: number;
  chunk_index: number;
};

export type ChatResponse = { answer: string; sources: ChatSource[] };


async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, { credentials: 'same-origin', ...init });
  if (!r.ok) {
    const text = await r.text().catch(() => '');
    throw new Error(`${r.status}: ${text || r.statusText}`);
  }
  return r.json();
}

export async function listArticles(p: ListParams = {}): Promise<{ count: number; total: number; articles: Article[]; limit: number; offset: number }> {
  const qs = new URLSearchParams();
  if (p.source) qs.set('source', p.source);
  if (p.since_days) qs.set('since_days', String(p.since_days));
  if (p.unread) qs.set('unread', 'true');
  if (p.starred) qs.set('starred', 'true');
  if (p.q) qs.set('q', p.q);
  if (p.limit) qs.set('limit', String(p.limit));
  if (p.offset) qs.set('offset', String(p.offset));
  if (p.order) qs.set('order', p.order);
  return req(`/api/news/list?${qs}`);
}

export async function getArticle(id: string): Promise<ArticleWithMarkdown> {
  return req(`/api/news/${id}`);
}

export async function setRead(id: string, value: boolean): Promise<Article> {
  return req(`/api/news/${id}/read`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
}

export async function setStarred(id: string, value: boolean): Promise<Article> {
  return req(`/api/news/${id}/star`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
}

export async function markAllRead(source?: string): Promise<{ marked_read: number; source: string | null }> {
  return req('/api/news/mark-all-read', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source: source ?? null }),
  });
}

export async function sources(): Promise<{ sources: SourceCount[] }> {
  return req('/api/news/sources');
}

export async function stats(): Promise<Stats> {
  return req('/api/news/stats');
}

export async function chat(question: string, opts: {
  top_k?: number;
  sources?: string[];
  since_days?: number;
  unread_only?: boolean;
} = {}): Promise<ChatResponse> {
  // Routes through n8n agent workflow (Caddy proxies /api/chat → n8n webhook).
  return req('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, ...opts }),
  });
}
