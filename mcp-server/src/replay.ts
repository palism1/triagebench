// FILE MAP
//   14-40  Types: the t0 snapshot, corpus entries and labels as exported by evals/export_replay.py
//   43-100 ReplayStore: loads every repo bundle under the replay dir; read-only lookups
//
// Purpose: serve frozen t0 data. Nothing here can see t1 (ground truth): the export script
// never writes it into a bundle.
//
// Bundle layout (one directory per repo):
//   bundle.json   {"full_name": "astral-sh/ruff", "split": "dev"}
//   issues.jsonl  one t0 snapshot per line
//   corpus.jsonl  {"number", "title", "body"} for every issue that is open at some t0
//   labels.json   [{"name", "description"}]
//   files/<sha>/<path>  optional file fixtures (tests); otherwise --git-dir is used

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface T0Issue {
  repo: string;
  number: number;
  url: string;
  created_at: string;
  title: string;
  body: string;
  author_association: string;
  labels_at_t0: string[];
  t0_sha: string;
  open_issues_at_t0: number[];
}

export interface CorpusEntry {
  number: number;
  title: string;
  body: string;
}

export interface Label {
  name: string;
  description: string;
}

export class NotFound extends Error {}

interface RepoBundle {
  dir: string;
  issues: Map<number, T0Issue>;
  corpus: Map<number, CorpusEntry>;
  labels: Label[];
}

function readJsonl<T>(path: string): T[] {
  return readFileSync(path, "utf8")
    .split("\n")
    .filter((l) => l.trim() !== "")
    .map((l) => JSON.parse(l) as T);
}

export class ReplayStore {
  private repos = new Map<string, RepoBundle>();

  constructor(root: string) {
    if (!existsSync(root)) return; // empty store: every lookup reports NotFound
    for (const name of readdirSync(root).sort()) {
      const dir = join(root, name);
      const metaPath = join(dir, "bundle.json");
      if (!existsSync(metaPath)) continue;
      const meta = JSON.parse(readFileSync(metaPath, "utf8")) as { full_name: string };
      this.repos.set(meta.full_name, {
        dir,
        issues: new Map(readJsonl<T0Issue>(join(dir, "issues.jsonl")).map((i) => [i.number, i])),
        corpus: new Map(readJsonl<CorpusEntry>(join(dir, "corpus.jsonl")).map((c) => [c.number, c])),
        labels: JSON.parse(readFileSync(join(dir, "labels.json"), "utf8")) as Label[],
      });
    }
  }

  repoNames(): string[] {
    return [...this.repos.keys()].sort();
  }

  private bundle(repo: string): RepoBundle {
    const b = this.repos.get(repo);
    if (!b) throw new NotFound(`repo ${repo} is not in the replay bundle`);
    return b;
  }

  bundleDir(repo: string): string {
    return this.bundle(repo).dir;
  }

  issue(repo: string, number: number): T0Issue {
    const i = this.bundle(repo).issues.get(number);
    if (!i) throw new NotFound(`issue ${repo}#${number} is not in the replay bundle`);
    return i;
  }

  labels(repo: string): Label[] {
    return this.bundle(repo).labels;
  }

  // DO NOT TOUCH: duplicate search may only see issues that were open when this issue was
  // created. Searching the whole corpus would leak later issues into the backtest.
  candidatesAtT0(repo: string, number: number): CorpusEntry[] {
    const b = this.bundle(repo);
    const issue = this.issue(repo, number);
    return issue.open_issues_at_t0
      .map((n) => b.corpus.get(n))
      .filter((c): c is CorpusEntry => c !== undefined);
  }
}
