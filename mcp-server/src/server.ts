// FILE MAP
//   18-35  helpers: ok / fail results with stable JSON text
//   38-60  get_issue
//   62-72  list_labels
//   74-95  search_dup
//   97-112 get_file
//   114-150 propose_label / propose_pr (gated by checkWrite, never write to GitHub)
//
// Purpose: the tool surface the triage agent sees. Every read is served from the t0 view of
// an issue; every write is a proposal for the human approval queue.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import type { ServerConfig } from "./config.js";
import { stableStringify } from "./json.js";
import type { ReplayStore } from "./replay.js";
import { rankBm25 } from "./tools/bm25.js";
import { readFileAtSha } from "./tools/files.js";
import { checkWrite, makeProposal } from "./tools/guard.js";

function ok(value: unknown): CallToolResult {
  return { content: [{ type: "text", text: stableStringify(value) }] };
}

function fail(err: unknown): CallToolResult {
  const message = err instanceof Error ? err.message : String(err);
  return { isError: true, content: [{ type: "text", text: message }] };
}

function guarded(fn: () => unknown): CallToolResult {
  try {
    return ok(fn());
  } catch (err) {
    return fail(err);
  }
}

const repo = z.string().regex(/^[\w.-]+\/[\w.-]+$/).describe("owner/name");
const number = z.number().int().positive().describe("issue number");

export function createServer(cfg: ServerConfig, store: ReplayStore): McpServer {
  const server = new McpServer({ name: "triagebench", version: "0.1.0" });

  server.registerTool(
    "get_issue",
    {
      description:
        "Read an issue as it looked when it was opened: title, body, author role, labels from the issue form, and the commit the repo was at.",
      inputSchema: { repo, number },
      annotations: { readOnlyHint: true },
    },
    async (a) =>
      guarded(() => {
        const { open_issues_at_t0, ...issue } = store.issue(a.repo, a.number);
        return { ...issue, open_issue_count: open_issues_at_t0.length };
      }),
  );

  server.registerTool(
    "list_labels",
    {
      description: "List the labels this repository uses, with descriptions. Only these may be proposed.",
      inputSchema: { repo },
      annotations: { readOnlyHint: true },
    },
    async (a) => guarded(() => store.labels(a.repo)),
  );

  server.registerTool(
    "search_dup",
    {
      description:
        "Find possible duplicates among issues that were open when this issue was created. Defaults to searching with the issue's own title and body.",
      inputSchema: {
        repo,
        number,
        query: z.string().optional().describe("override the search text"),
        k: z.number().int().min(1).max(20).default(5),
      },
      annotations: { readOnlyHint: true },
    },
    async (a) =>
      guarded(() => {
        const issue = store.issue(a.repo, a.number);
        const query = a.query ?? `${issue.title}\n${issue.body}`;
        return rankBm25(query, store.candidatesAtT0(a.repo, a.number), a.k);
      }),
  );

  server.registerTool(
    "get_file",
    {
      description: "Read a file from the repository at the commit it was at when this issue was opened.",
      inputSchema: { repo, number, path: z.string().min(1) },
      annotations: { readOnlyHint: true },
    },
    async (a) =>
      guarded(() => {
        const issue = store.issue(a.repo, a.number);
        const text = readFileAtSha(a.repo, issue.t0_sha, a.path, store.bundleDir(a.repo), cfg.gitDir);
        return { path: a.path, sha: issue.t0_sha, content: text };
      }),
  );

  server.registerTool(
    "propose_label",
    {
      description: "Propose labels for an issue. Nothing is applied: the proposal goes to a human for approval.",
      inputSchema: {
        repo,
        number,
        labels: z.array(z.string().min(1)).min(1),
        rationale: z.string().min(1),
      },
    },
    async (a) =>
      guarded(() => {
        const mode = checkWrite(cfg, a.repo);
        store.issue(a.repo, a.number); // must exist
        const labels = [...new Set(a.labels)].sort();
        return makeProposal("label", a.repo, a.number, { labels, rationale: a.rationale }, mode);
      }),
  );

  server.registerTool(
    "propose_pr",
    {
      description: "Propose a fix as a unified diff. Nothing is pushed: the proposal goes to a human for approval.",
      inputSchema: {
        repo,
        number,
        title: z.string().min(1),
        diff: z.string().min(1),
        rationale: z.string().min(1),
      },
    },
    async (a) =>
      guarded(() => {
        const mode = checkWrite(cfg, a.repo);
        store.issue(a.repo, a.number);
        return makeProposal(
          "pr",
          a.repo,
          a.number,
          { title: a.title, diff: a.diff, rationale: a.rationale },
          mode,
        );
      }),
  );

  return server;
}
