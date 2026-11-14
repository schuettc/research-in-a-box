import { expect, test } from "vitest";
import { contrast, shades } from "./brand";

const COLOURS = [
  "#24395f",
  "#1e5631",
  "#0b5cad",
  "#ffd33d",
  "#777777",
  "#ff0000",
  "#00ffff",
  "#000000",
  "#ffffff",
  "#8a4d12",
  "#6f42c1",
];

test.each(COLOURS)("text on %s and its hover and active shades meets AA", (colour) => {
  const { ink, hover, active } = shades(colour);

  for (const background of [colour, hover, active]) {
    expect(contrast(ink, background)).toBeGreaterThanOrEqual(4.5);
  }
  expect(hover).not.toBe(colour);
  expect(active).not.toBe(hover);
});

test("the default navy takes white text and darker hover shades", () => {
  const { ink, hover } = shades("#24395f");

  expect(ink).toBe("#ffffff");
  expect(contrast("#ffffff", hover)).toBeGreaterThan(contrast("#ffffff", "#24395f"));
});
