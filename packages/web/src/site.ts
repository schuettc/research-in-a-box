/** The archive's name, intro, contact and logo, from the config's `brand:` block at build time. */
declare const __BRAND__: {
  name: string;
  intro: string | null;
  contact: string | null;
  logo: string | null;
};
declare const __PUBLISHER__: string;

export const BRAND = __BRAND__;
export const PUBLISHER = __PUBLISHER__;
