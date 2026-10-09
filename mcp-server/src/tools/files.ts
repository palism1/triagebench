// FILE MAP
//   12-25  safePath: reject traversal and absolute paths
//   28-60  readFileAtSha: fixture directory first, then a local bare clone via `git show`
//
// Purpose: get_file returns a file exactly as it was at the issue's t0 commit, never HEAD.

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join, normalize } from "node:path";

// TWEAK: cap returned file size so one call cannot flood the model's context.
export const MAX_FILE_BYTES = 200_000;

export function safePath(path: string): string {
  const p = normalize(path).replace(/^\.\/+/, "");
  if (p.startsWith("/") || p.startsWith("..") || p.includes("/../") || p === "..") {
    throw new Error(`path ${path} escapes the repository`);
  }
  return p;
}

export function readFileAtSha(
  repo: string,
  sha: string,
  path: string,
  bundleDir: string,
  gitDir?: string,
): string {
  const p = safePath(path);
  if (!/^[0-9a-f]{7,40}$/.test(sha)) throw new Error(`bad sha ${sha}`);
  const fixture = join(bundleDir, "files", sha, p);
  let content: Buffer;
  if (existsSync(fixture)) {
    content = readFileSync(fixture);
  } else if (gitDir) {
    const bare = join(gitDir, `${repo.replace("/", "__")}.git`);
    // execFileSync with an argv array: no shell, so the path cannot inject commands.
    content = execFileSync("git", ["--git-dir", bare, "show", `${sha}:${p}`], {
      maxBuffer: MAX_FILE_BYTES * 4,
    });
  } else {
    throw new Error(`file ${p}@${sha} not in fixtures and no --git-dir configured`);
  }
  const text = content.toString("utf8");
  return content.length > MAX_FILE_BYTES
    ? `${text.slice(0, MAX_FILE_BYTES)}\n[truncated: ${content.length} bytes]`
    : text;
}
