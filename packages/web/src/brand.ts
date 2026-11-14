/**
 * The shades derived from the brand's primary colour, shared by the app's stylesheet and the
 * sign-in page's branding so both press the same button colour: the text on it (white or
 * black, whichever reads better) and its hover and active shades, each moved away from that
 * text so the contrast only grows (or, for pure black or white, a little toward it).
 */

const DARK = "#000000";
const LIGHT = "#ffffff";

function channels(hex: string): [number, number, number] {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function toHex(rgb: number[]): string {
  return `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((c) => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The WCAG contrast ratio of two `#rrggbb` colours. */
export function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}

function mix(hex: string, toward: string, amount: number): string {
  const from = channels(hex);
  const to = channels(toward);
  return toHex(from.map((c, i) => c + ((to[i] ?? c) - c) * amount));
}

export interface Shades {
  /** Text on the primary colour. */
  ink: string;
  hover: string;
  active: string;
}

export function shades(primary: string): Shades {
  const colour = primary.toLowerCase();
  const ink = contrast(LIGHT, colour) >= contrast(DARK, colour) ? LIGHT : DARK;
  const away = ink === LIGHT ? DARK : LIGHT;
  const toward = mix(colour, away, 0.15) === colour ? ink : away;
  return { ink, hover: mix(colour, toward, 0.15), active: mix(colour, toward, 0.3) };
}
