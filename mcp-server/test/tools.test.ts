// FILE MAP
//   10-25  tool listing
//   27-50  get_issue / list_labels contracts
//   52-80  search_dup: t0 universe only, ranking, determinism
//   82-105 get_file: t0 SHA, traversal refused

import { describe, expect, it } from "vitest";
import { call, connect, REPO } from "./helpers.js";

describe("tool surface", () => {
  it("lists exactly the Week 2 tools", async () => {
    const client = await connect();
    const names = (await client.listTools()).tools.map((t) => t.name).sort();
    expect(names).toEqual(["get_file", "get_issue", "list_labels", "propose_label", "propose_pr", "search_dup"]);
  });
});

describe("get_issue", () => {
  it("returns the t0 view without the open-issue list", async () => {
    const r = await call(await connect(), "get_issue", { repo: REPO, number: 12 });
    expect(r.isError).toBe(false);
    expect(r.json).toMatchObject({ number: 12, labels_at_t0: ["kind/bug"], t0_sha: "a1b2c3d", open_issue_count: 4 });
    expect(r.json).not.toHaveProperty("open_issues_at_t0");
  });

  it("reports unknown issues and repos as errors", async () => {
    const client = await connect();
    expect((await call(client, "get_issue", { repo: REPO, number: 999 })).isError).toBe(true);
    expect((await call(client, "get_issue", { repo: "acme/nope", number: 12 })).text).toMatch(/not in the replay bundle/);
  });
});

describe("list_labels", () => {
  it("returns the repo's label set sorted", async () => {
    const r = await call(await connect(), "list_labels", { repo: REPO });
    expect((r.json as Array<{ name: string }>).map((l) => l.name)).toEqual(["area/docs", "area/solver", "duplicate", "kind/bug"]);
  });
});

describe("search_dup", () => {
  it("ranks the real duplicate first and never returns issues opened later", async () => {
    const r = await call(await connect(), "search_dup", { repo: REPO, number: 12, k: 10 });
    const nums = (r.json as Array<{ number: number }>).map((x) => x.number);
    expect(nums[0]).toBe(3);
    expect(nums).not.toContain(20); // filed after #12: would leak the future
    expect(nums).not.toContain(12);
  });

  it("only searches issues open at that issue's t0", async () => {
    const r = await call(await connect(), "search_dup", { repo: REPO, number: 8, query: "solver circular" });
    const nums = (r.json as Array<{ number: number }>).map((x) => x.number);
    expect(nums).toEqual([3]); // #11 was not open yet when #8 was filed
  });

  it("is deterministic across calls and servers", async () => {
    const a = await call(await connect(), "search_dup", { repo: REPO, number: 12 });
    const b = await call(await connect(), "search_dup", { repo: REPO, number: 12 });
    expect(a.text).toBe(b.text);
  });
});

describe("get_file", () => {
  it("reads the file at the issue's t0 commit", async () => {
    const r = await call(await connect(), "get_file", { repo: REPO, number: 12, path: "src/solver.py" });
    expect(r.json).toMatchObject({ sha: "a1b2c3d", path: "src/solver.py" });
    expect((r.json as { content: string }).content).toContain("def resolve");
  });

  it("refuses paths outside the repository", async () => {
    const client = await connect();
    for (const path of ["../secrets", "/etc/passwd", "src/../../x"]) {
      const r = await call(client, "get_file", { repo: REPO, number: 12, path });
      expect(r.isError, path).toBe(true);
    }
  });
});
