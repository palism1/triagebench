// FILE MAP
//   6-25  BM25 unit tests: empty inputs, tie-break by issue number.

import { describe, expect, it } from "vitest";
import { rankBm25, tokenize } from "../src/tools/bm25.js";

describe("bm25", () => {
  it("tokenizes to lowercase words", () => {
    expect(tokenize("RecursionError in `solver.py`!")).toEqual(["recursionerror", "in", "solver", "py"]);
  });

  it("returns nothing for empty corpus or query", () => {
    expect(rankBm25("x", [], 5)).toEqual([]);
    expect(rankBm25("", [{ number: 1, title: "a", body: "b" }], 5)).toEqual([]);
  });

  it("breaks score ties by issue number", () => {
    const docs = [2, 1, 3].map((n) => ({ number: n, title: "same words", body: "" }));
    expect(rankBm25("same", docs, 3).map((r) => r.number)).toEqual([1, 2, 3]);
  });
});
