// FILE MAP
//   10-35  connect: an in-process MCP client wired to a server over the fixture bundle
//   37-45  call: invoke a tool and return parsed JSON (or the error text)
//
// Purpose: contract tests talk to the server through the real MCP protocol, not internals.

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { fileURLToPath } from "node:url";
import { parseArgs } from "../src/config.js";
import { ReplayStore } from "../src/replay.js";
import { createServer } from "../src/server.js";

export const FIXTURES = fileURLToPath(new URL("./fixtures/replay", import.meta.url));
export const REPO = "acme/widgets";

export async function connect(args: string[] = []): Promise<Client> {
  const cfg = parseArgs(["--replay-dir", FIXTURES, ...args], {});
  const server = createServer(cfg, new ReplayStore(cfg.replayDir));
  const [clientT, serverT] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: "test", version: "0" });
  await Promise.all([server.connect(serverT), client.connect(clientT)]);
  return client;
}

export interface CallResult {
  isError: boolean;
  text: string;
  json: unknown;
}

export async function call(client: Client, name: string, args: Record<string, unknown>): Promise<CallResult> {
  const res = await client.callTool({ name, arguments: args });
  const content = res.content as Array<{ type: string; text: string }>;
  const text = content[0]?.text ?? "";
  let json: unknown = undefined;
  try {
    json = JSON.parse(text);
  } catch {
    /* error messages are plain text */
  }
  return { isError: Boolean(res.isError), text, json };
}
