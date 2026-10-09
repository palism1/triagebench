#!/usr/bin/env node
// FILE MAP
//   9-25  main: parse flags, load the replay bundle, serve over stdio
//
// Purpose: entry point. `node dist/index.js --replay-dir <dir>` (replay, dry-run) is the default.
// Live mode still reads from replay data; it only changes what writes may do.

import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { parseArgs } from "./config.js";
import { ReplayStore } from "./replay.js";
import { createServer } from "./server.js";

async function main(): Promise<void> {
  const cfg = parseArgs(process.argv.slice(2));
  const store = new ReplayStore(cfg.replayDir);
  const server = createServer(cfg, store);
  await server.connect(new StdioServerTransport());
  // stderr only: stdout is the MCP channel.
  console.error(
    `triagebench MCP: mode=${cfg.mode} approve=${cfg.approve} repos=${store.repoNames().join(",") || "none"}`,
  );
}

main().catch((err: unknown) => {
  console.error(err);
  process.exit(1);
});
