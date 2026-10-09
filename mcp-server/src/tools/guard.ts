// FILE MAP
//   12-20  WriteRefused: the error every refused write raises
//   23-45  checkWrite: replay -> dry-run; live -> needs --approve AND an allowlisted repo
//   48-70  makeProposal: deterministic proposal record (id = hash of its content)
//
// Purpose: the write gate. propose_* tools never touch GitHub; they return a
// proposal for the approval queue. This module decides whether a live write could ever run.

import { createHash } from "node:crypto";
import type { ServerConfig } from "../config.js";
import { stableStringify } from "../json.js";

export class WriteRefused extends Error {}

export type WriteMode = "dry-run" | "live";

// DO NOT TOUCH: order matters. The allowlist check runs even when --approve is set, so an
// approved session still cannot write to a repo that was not explicitly allowed.
export function checkWrite(cfg: ServerConfig, repo: string): WriteMode {
  if (cfg.mode === "replay") return "dry-run";
  if (!cfg.allowRepos.includes(repo)) {
    throw new WriteRefused(`refused: ${repo} is not in the --allow-repo allowlist`);
  }
  if (!cfg.approve) {
    throw new WriteRefused("refused: live writes require the --approve flag");
  }
  return "live";
}

export interface Proposal {
  id: string;
  kind: "label" | "pr";
  repo: string;
  number: number;
  payload: Record<string, unknown>;
  mode: WriteMode;
  status: "pending_approval";
}

export function makeProposal(
  kind: Proposal["kind"],
  repo: string,
  number: number,
  payload: Record<string, unknown>,
  mode: WriteMode,
): Proposal {
  const id = createHash("sha256")
    .update(stableStringify({ kind, repo, number, payload }))
    .digest("hex")
    .slice(0, 16);
  return { id, kind, repo, number, payload, mode, status: "pending_approval" };
}
