import { readFileSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { parse } from "yaml";
import { defineConfig } from "vitest/config";
import { shades } from "./src/brand";

const ARCHIVE_YAML = fileURLToPath(new URL("../../archive.yaml", import.meta.url));
const INDEX_HTML = fileURLToPath(new URL("index.html", import.meta.url));
const BRAND_CSS = "virtual:brand.css";
const DEFAULT_PRIMARY = "#24395f";

interface BrandBlock {
  name?: string;
  intro?: string;
  contact?: string;
  logo?: string;
  favicon?: string;
  primaryColor?: string;
  font?: string;
}

/** The brand as the app is built with it: the archive config's `brand:` block, with defaults. */
interface Brand {
  publisher: string;
  name: string;
  intro: string | null;
  contact: string | null;
  primaryColor: string;
  font: string | null;
  /** The brand's files on disk, by the name they are served at under `/brand/`. */
  files: Map<string, string>;
}

/** The archive config: `ARCHIVE_CONFIG` when set, as the infra app reads it. */
function readBrand(): Brand {
  const path = process.env.ARCHIVE_CONFIG ?? ARCHIVE_YAML;
  const config = parse(readFileSync(path, "utf-8")) as { publisher?: unknown; brand?: BrandBlock };
  if (typeof config.publisher !== "string") throw new Error("the archive config has no publisher");
  const brand = config.brand ?? {};
  const primaryColor = brand.primaryColor ?? DEFAULT_PRIMARY;
  // The contract validates these; checked again here because they are written into CSS.
  if (!/^#[0-9a-fA-F]{6}$/.test(primaryColor)) throw new Error("brand.primaryColor isn't #rrggbb");
  if (brand.font !== undefined && !/^[\w \-,'"]+$/.test(brand.font)) {
    throw new Error("brand.font isn't a CSS font-family list");
  }
  const files = new Map<string, string>();
  for (const kind of ["logo", "favicon"] as const) {
    const file = brand[kind];
    if (file) files.set(`${kind}${extname(file).toLowerCase()}`, resolve(dirname(path), file));
  }
  return {
    publisher: config.publisher,
    name: brand.name ?? config.publisher,
    intro: brand.intro ?? null,
    contact: brand.contact ?? null,
    primaryColor,
    font: brand.font ?? null,
    files,
  };
}

function brandUrl(brand: Brand, kind: "logo" | "favicon"): string | null {
  const name = [...brand.files.keys()].find((file) => file.startsWith(`${kind}.`));
  return name ? `/brand/${name}` : null;
}

/** The `:root` properties the brand sets, after `styles.css`'s defaults. */
function brandCss(brand: Brand): string {
  const { ink, hover, active } = shades(brand.primaryColor);
  const font = brand.font ? `--font-heading:${brand.font};` : "";
  return (
    `:root{--brand:${brand.primaryColor};--brand-ink:${ink};` +
    `--brand-hover:${hover};--brand-active:${active};${font}}\n`
  );
}

const escapeHtml = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** `index.html` with the brand's name as its title and its favicon. */
function brandHtml(brand: Brand, html: string): string {
  const favicon = brandUrl(brand, "favicon");
  const icon = favicon ? `<link rel="icon" href="${favicon}" />\n    ` : "";
  return html.replace(/<title>[^<]*<\/title>/, `${icon}<title>${escapeHtml(brand.name)}</title>`);
}

const CONTENT_TYPES: Record<string, string> = {
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

/**
 * The brand at build time: `virtual:brand.css` holds its colours and font, its logo and favicon
 * are copied to `/brand/`, and `index.html` takes its name and favicon.
 */
function branding(brand: Brand): Plugin {
  return {
    name: "brand",
    resolveId(id) {
      return id === BRAND_CSS ? `\0${BRAND_CSS}` : null;
    },
    load(id) {
      return id === `\0${BRAND_CSS}` ? brandCss(brand) : null;
    },
    configureServer(server) {
      server.middlewares.use("/brand", (request, response, next) => {
        const file = brand.files.get((request.url ?? "").replace(/^\//, ""));
        if (!file) return next();
        response.setHeader("Content-Type", CONTENT_TYPES[extname(file).toLowerCase()] ?? "");
        response.end(readFileSync(file));
      });
    },
    transformIndexHtml(html) {
      return brandHtml(brand, html);
    },
    generateBundle() {
      for (const [name, file] of brand.files) {
        this.emitFile({ type: "asset", fileName: `brand/${name}`, source: readFileSync(file) });
      }
    },
  };
}

/**
 * Emits `/app.js`, the one stable URL `index.html` and every dataset page load: it imports the
 * hashed entry chunk and adds the hashed stylesheet, both named here at build time. `index.html`
 * is copied with the brand's title and favicon, so it never names a hashed file. In dev,
 * `/app.js` imports the source.
 */
function loader(brand: Brand): Plugin {
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
      const html = brandHtml(brand, readFileSync(INDEX_HTML, "utf-8"));
      this.emitFile({ type: "asset", fileName: "index.html", source: html });
    },
  };
}

const brand = readBrand();

export default defineConfig({
  plugins: [react(), branding(brand), loader(brand)],
  define: {
    __PUBLISHER__: JSON.stringify(brand.publisher),
    __BRAND__: JSON.stringify({
      name: brand.name,
      intro: brand.intro,
      contact: brand.contact,
      logo: brandUrl(brand, "logo"),
    }),
  },
  build: { rolldownOptions: { input: "src/main.tsx" } },
  test: {
    environment: "jsdom",
  },
});
