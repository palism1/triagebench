// FILE MAP
//   9-15   tokenize: lowercase word tokens
//   18-60  rankBm25: Okapi BM25 over title (weighted) + body, ties broken by issue number
//
// Purpose: a deterministic, dependency-free duplicate retriever. Embeddings can replace it
// later; the contract (top-k candidates with scores) stays the same.

import type { CorpusEntry } from "../replay.js";

export function tokenize(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9_]+/g) ?? [];
}

// TWEAK: standard BM25 constants; title counted twice because titles carry most of the signal.
const K1 = 1.2;
const B = 0.75;
const TITLE_WEIGHT = 2;

export interface Ranked {
  number: number;
  title: string;
  score: number;
}

export function rankBm25(query: string, docs: CorpusEntry[], k: number): Ranked[] {
  const qTerms = [...new Set(tokenize(query))];
  const docTokens = docs.map((d) => [
    ...Array<string[]>(TITLE_WEIGHT).fill(tokenize(d.title)).flat(),
    ...tokenize(d.body),
  ]);
  const n = docs.length;
  if (n === 0 || qTerms.length === 0) return [];
  const avgLen = docTokens.reduce((s, t) => s + t.length, 0) / n || 1;
  const df = new Map<string, number>();
  for (const toks of docTokens) for (const t of new Set(toks)) df.set(t, (df.get(t) ?? 0) + 1);

  const ranked = docs.map((d, i) => {
    const toks = docTokens[i] ?? [];
    const tf = new Map<string, number>();
    for (const t of toks) tf.set(t, (tf.get(t) ?? 0) + 1);
    let score = 0;
    for (const q of qTerms) {
      const f = tf.get(q) ?? 0;
      if (f === 0) continue;
      const idf = Math.log(1 + (n - (df.get(q) ?? 0) + 0.5) / ((df.get(q) ?? 0) + 0.5));
      score += (idf * f * (K1 + 1)) / (f + K1 * (1 - B + (B * toks.length) / avgLen));
    }
    return { number: d.number, title: d.title, score: Math.round(score * 1e6) / 1e6 };
  });
  return ranked
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score || a.number - b.number)
    .slice(0, k);
}
