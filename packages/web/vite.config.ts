import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { parse } from "yaml";
import { defineConfig } from "vitest/config";

const ARCHIVE_YAML = fileURLToPath(new URL("../../archive.yaml", import.meta.url));
const INDEX_HTML = fileURLToPath(new URL("index.html", import.meta.url));

/** The publisher from the archive config: `ARCHIVE_CONFIG` when set, as the infra app reads it. */
function publisher(): string {
  const config = parse(readFileSync(process.env.ARCHIVE_CONFIG ?? ARCHIVE_YAML, "utf-8")) as {
    publisher?: unknown;
  };
  if (typeof config.publisher !== "string") throw new Error("the archive config has no publisher");
  return config.publisher;
}

/**
 * Emits `/app.js`, the one stable URL `index.html` and every dataset page load: it imports the
 * hashed entry chunk and adds the hashed stylesheet, both named here at build time. `index.html`
 * is copied as written, so it never names a hashed file. In dev, `/app.js` imports the source.
 */
function loader(): Plugin {
  return {
    name: "app-loader",
    enforce: "post",
    configureServer(server) {
      server.middlewares.use("/app.js", (_request, response) => {
        response.setHeader("Content-Type", "text/javascript");
        response.end('import "/src/main.tsx";\n');
      });
    },
    generateBundle(_options, bundle) {
      const entry = Object.values(bundle).find((file) => file.type === "chunk" && file.isEntry);
      if (!entry || entry.type !== "chunk") throw new Error("the build has no entry chunk");
      const styles = [...(entry.viteMetadata?.importedCss ?? [])].map(
        (css) =>
          `{ const link = document.createElement("link"); link.rel = "stylesheet"; ` +
          `link.href = ${JSON.stringify(`/${css}`)}; document.head.append(link); }\n`,
      );
      const source = `${styles.join("")}import ${JSON.stringify(`/${entry.fileName}`)};\n`;
      this.emitFile({ type: "asset", fileName: "app.js", source });
      this.emitFile({ type: "asset", fileName: "index.html", source: readFileSync(INDEX_HTML) });
    },
  };
}

export default defineConfig({
  plugins: [react(), loader()],
  define: { __PUBLISHER__: JSON.stringify(publisher()) },
  build: { rolldownOptions: { input: "src/main.tsx" } },
  test: {
    environment: "jsdom",
  },
});
