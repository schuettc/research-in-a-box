import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "./App";

test("App renders the kit's title", () => {
  render(<App />);

  expect(screen.getByRole("heading", { name: "research-in-a-box" })).toBeDefined();
});
