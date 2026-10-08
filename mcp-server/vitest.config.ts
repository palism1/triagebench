// FILE MAP
//   5-10  vitest config: tests live in test/, run in Node.
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { include: ["test/**/*.test.ts"], environment: "node" },
});
