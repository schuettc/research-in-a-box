import { existsSync, readFileSync } from "node:fs";
import { extname, resolve } from "node:path";
import type * as cognito from "aws-cdk-lib/aws-cognito";
import { shades } from "../../web/src/brand";
import type { ArchiveConfig } from "./generated/archive-config";

/** The app's default primary colour (`--brand` in the web app's styles.css). */
export const DEFAULT_PRIMARY = "#24395f";
/** The app's focus ring (`--focus` in styles.css), so focus looks the same on both. */
const FOCUS = "#c26a00";
/** Cognito takes at most this many base64 characters per asset. */
const MAX_ASSET_CHARS = 1_000_000;

export interface BrandFile {
  readonly extension: "SVG" | "PNG" | "ICO";
  /** The file, base64. */
  readonly bytes: string;
}

/** What managed login and the invitation email take from the archive config's `brand:` block. */
export interface LoginBrand {
  readonly name: string;
  readonly primaryColor: string;
  readonly logo?: BrandFile;
  readonly favicon?: BrandFile;
}

function brandFile(kind: "logo" | "favicon", path: string, configDir: string): BrandFile {
  const file = resolve(configDir, path);
  if (!existsSync(file)) throw new Error(`brand: no ${kind} file at ${file}`);
  const extension = extname(file).slice(1).toUpperCase();
  const allowed = kind === "logo" ? ["SVG", "PNG"] : ["SVG", "ICO"];
  if (!allowed.includes(extension)) {
    throw new Error(`brand: the ${kind} must be ${allowed.join(" or ").toLowerCase()}: ${file}`);
  }
  const bytes = readFileSync(file).toString("base64");
  if (bytes.length > MAX_ASSET_CHARS) {
    throw new Error(
      `brand: the ${kind} ${file} is too big for the sign-in page: ${bytes.length} base64 ` +
        `characters, and Cognito takes at most ${MAX_ASSET_CHARS}`,
    );
  }
  return { extension: extension as BrandFile["extension"], bytes };
}

/** The config's brand, with its files read from paths relative to `configDir`. */
export function loginBrand(config: ArchiveConfig, configDir: string): LoginBrand {
  const brand = config.brand ?? {};
  const found: { -readonly [K in keyof LoginBrand]: LoginBrand[K] } = {
    name: brand.name ?? config.publisher,
    primaryColor: (brand.primaryColor ?? DEFAULT_PRIMARY).toLowerCase(),
  };
  if (brand.logo) found.logo = brandFile("logo", brand.logo, configDir);
  if (brand.favicon) found.favicon = brandFile("favicon", brand.favicon, configDir);
  return found;
}

/** `#rrggbb` as managed login's `rrggbbaa`. */
const rgba = (hex: string) => `${hex.slice(1).toLowerCase()}ff`;

/**
 * Managed login's settings document: the primary button with the app's shades, links in the
 * brand colour, the app's focus ring, the form logo on, light mode and no page header. Cognito
 * keeps its defaults for every setting left out.
 */
export function brandingSettings(brand: LoginBrand): Record<string, unknown> {
  const { ink, hover, active } = shades(brand.primaryColor);
  const button = (background: string) => ({
    backgroundColor: rgba(background),
    textColor: rgba(ink),
  });
  return {
    categories: {
      global: {
        colorSchemeMode: "LIGHT",
        pageHeader: { enabled: false },
        pageFooter: { enabled: false },
      },
    },
    componentClasses: {
      focusState: { lightMode: { borderColor: rgba(FOCUS) } },
      link: {
        lightMode: {
          defaults: { textColor: rgba(brand.primaryColor) },
          hover: { textColor: rgba(hover) },
        },
      },
    },
    components: {
      primaryButton: {
        lightMode: {
          defaults: button(brand.primaryColor),
          hover: button(hover),
          active: button(active),
        },
      },
      form: {
        logo: { enabled: true, formInclusion: "IN", location: "CENTER", position: "TOP" },
      },
      ...(brand.favicon && { favicon: { enabledTypes: [brand.favicon.extension] } }),
    },
  };
}

/** The logo as the form's logo and the favicon, in light mode. */
export function brandingAssets(
  brand: LoginBrand,
): cognito.CfnManagedLoginBranding.AssetTypeProperty[] {
  const assets: cognito.CfnManagedLoginBranding.AssetTypeProperty[] = [];
  if (brand.logo) {
    assets.push({
      category: "FORM_LOGO",
      colorMode: "LIGHT",
      extension: brand.logo.extension,
      bytes: brand.logo.bytes,
    });
  }
  if (brand.favicon) {
    assets.push({
      category: brand.favicon.extension === "ICO" ? "FAVICON_ICO" : "FAVICON_SVG",
      colorMode: "LIGHT",
      extension: brand.favicon.extension,
      bytes: brand.favicon.bytes,
    });
  }
  return assets;
}
