// FILE MAP
//   10-30  replay mode: proposals are dry-run and deterministic
//   32-60  live mode: allowlist and --approve are both required
//   62-75  argument parsing defaults

import { describe, expect, it } from "vitest";
import { parseArgs } from "../src/config.js";
import { call, connect, REPO } from "./helpers.js";

const LABEL = { repo: REPO, number: 12, labels: ["area/solver", "kind/bug"], rationale: "solver recursion" };

describe("replay mode writes", () => {
  it("returns a dry-run proposal and touches nothing", async () => {
    const r = await call(await connect(), "propose_label", LABEL);
    expect(r.isError).toBe(false);
    expect(r.json).toMatchObject({ kind: "label", mode: "dry-run", status: "pending_approval" });
  });

  it("gives identical proposal ids for identical proposals", async () => {
    const a = await call(await connect(), "propose_label", LABEL);
    const b = await call(await connect(), "propose_label", { ...LABEL, labels: ["kind/bug", "area/solver"] });
    expect(a.text).toBe(b.text);
  });

  it("rejects proposals for issues not in the bundle", async () => {
    const r = await call(await connect(), "propose_pr", { repo: REPO, number: 404, title: "t", diff: "d", rationale: "r" });
    expect(r.isError).toBe(true);
  });
});

describe("live mode writes", () => {
  it("refuses repos outside the allowlist even with --approve", async () => {
    const client = await connect(["--mode", "live", "--approve", "--allow-repo", "palism1/sandbox"]);
    const r = await call(client, "propose_label", LABEL);
    expect(r.isError).toBe(true);
    expect(r.text).toMatch(/allowlist/);
  });

  it("refuses allowlisted repos without --approve", async () => {
    const r = await call(await connect(["--mode", "live", "--allow-repo", REPO]), "propose_pr", {
      repo: REPO, number: 12, title: "Fix recursion", diff: "--- a\n+++ b", rationale: "r",
    });
    expect(r.isError).toBe(true);
    expect(r.text).toMatch(/--approve/);
  });

  it("allows an approved, allowlisted repo (still only a proposal)", async () => {
    const r = await call(await connect(["--mode", "live", "--approve", "--allow-repo", REPO]), "propose_label", LABEL);
    expect(r.json).toMatchObject({ mode: "live", status: "pending_approval" });
  });
});

describe("parseArgs", () => {
  it("defaults to replay, no approval, empty allowlist", () => {
    const cfg = parseArgs([], {});
    expect(cfg).toMatchObject({ mode: "replay", approve: false, allowRepos: [] });
  });

  it("rejects unknown flags and modes", () => {
    expect(() => parseArgs(["--yolo"], {})).toThrow();
    expect(() => parseArgs(["--mode", "prod"], {})).toThrow();
  });
});
