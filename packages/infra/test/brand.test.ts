import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";
import { shades } from "../../web/src/brand";
import { brandingAssets, brandingSettings, DEFAULT_PRIMARY, loginBrand } from "../src/brand";

const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const STYLES = fileURLToPath(new URL("../../web/src/styles.css", import.meta.url));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = Record<string, any>;

test("the brand block's name, colour, logo and favicon reach the sign-in brand", () => {
  const brand = loginBrand(
    {
      publisher: "Invented Research Cooperative",
      brand: {
        name: "Lake Archive",
        primaryColor: "#0B5CAD",
        logo: "examples/brand/logo.svg",
        favicon: "examples/brand/favicon.svg",
      },
    },
    REPO,
  );

  expect(brand.name).toBe("Lake Archive");
  expect(brand.primaryColor).toBe("#0b5cad");
  expect(brand.logo?.extension).toBe("SVG");
  expect(Buffer.from(brand.logo?.bytes ?? "", "base64").toString("utf-8")).toBe(
    readFileSync(join(REPO, "examples/brand/logo.svg"), "utf-8"),
  );
  expect(brand.favicon?.extension).toBe("SVG");
});

test("no brand block gives the publisher's name and the app's default colour", () => {
  const brand = loginBrand({ publisher: "P" }, REPO);

  expect(brand).toEqual({ name: "P", primaryColor: DEFAULT_PRIMARY });
  expect(readFileSync(STYLES, "utf-8")).toContain(`--brand: ${DEFAULT_PRIMARY};`);
});

test("the sign-in page's button colours come from the same shade function as the app's", () => {
  for (const colour of ["#24395f", "#ffd33d", "#1e5631"]) {
    const settings = brandingSettings({ name: "A", primaryColor: colour }) as Json;
    const button = settings.components.primaryButton.lightMode;
    const { ink, hover, active } = shades(colour);
    const rgba = (hex: string) => `${hex.slice(1)}ff`;

    expect(button.defaults).toEqual({ backgroundColor: rgba(colour), textColor: rgba(ink) });
    expect(button.hover).toEqual({ backgroundColor: rgba(hover), textColor: rgba(ink) });
    expect(button.active).toEqual({ backgroundColor: rgba(active), textColor: rgba(ink) });
    expect(settings.componentClasses.link.lightMode.defaults.textColor).toBe(rgba(colour));
  }
});

test("the settings show the form logo, in light mode, with no page header", () => {
  const settings = brandingSettings({ name: "A", primaryColor: "#24395f" }) as Json;

  expect(settings.categories.global.colorSchemeMode).toBe("LIGHT");
  expect(settings.categories.global.pageHeader.enabled).toBe(false);
  expect(settings.components.form.logo.enabled).toBe(true);
});

test("the assets are the logo as FORM_LOGO and the favicon in its own category", () => {
  const brand = loginBrand(
    {
      publisher: "P",
      brand: { logo: "examples/brand/logo.svg", favicon: "examples/brand/favicon.svg" },
    },
    REPO,
  );

  expect(brandingAssets(brand).map((a) => [a.category, a.extension, a.colorMode])).toEqual([
    ["FORM_LOGO", "SVG", "LIGHT"],
    ["FAVICON_SVG", "SVG", "LIGHT"],
  ]);
  expect(brandingAssets({ name: "P", primaryColor: DEFAULT_PRIMARY })).toEqual([]);
});

test("synth stops with a plain message when an asset is over Cognito's limit", () => {
  const dir = mkdtempSync(join(tmpdir(), "brand-"));
  writeFileSync(join(dir, "big.png"), Buffer.alloc(800_000));

  expect(() => loginBrand({ publisher: "P", brand: { logo: "big.png" } }, dir)).toThrow(
    /logo .*too big for the sign-in page/,
  );
  expect(() => loginBrand({ publisher: "P", brand: { logo: "missing.svg" } }, dir)).toThrow(
    /no logo file/,
  );
});

test("the sign-in page has the app's paper as a plain background and no stock image", () => {
  const settings = brandingSettings({ name: "A", primaryColor: "#24395f" }) as Json;
  const paper = /--paper:\s*#([0-9a-f]{6})/i.exec(readFileSync(STYLES, "utf-8"))?.[1];

  expect(settings.components.pageBackground.image.enabled).toBe(false);
  expect(settings.components.pageBackground.lightMode.color).toBe(`${paper?.toLowerCase()}ff`);
});

test("the sign-in page's secondary button (Not now, Use password instead) is in the brand colour", () => {
  const settings = brandingSettings({ name: "A", primaryColor: "#8a2d3b" }) as Json;
  const secondary = settings.components.secondaryButton.lightMode.defaults;

  expect(secondary.borderColor).toBe("8a2d3bff");
  expect(secondary.textColor).toBe("8a2d3bff");
  expect(secondary.backgroundColor).toBe("ffffffff");
});
