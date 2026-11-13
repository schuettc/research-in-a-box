import { defineConfig } from "vitest/config";

export default defineConfig({
  // Each infra test synthesizes a whole stack; on CI a file took up to 7 seconds.
  test: { testTimeout: 30_000 },
});
