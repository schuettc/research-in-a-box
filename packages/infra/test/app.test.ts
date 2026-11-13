import { expect, test } from "vitest";
import { createApp, STACK_NAME } from "../bin/app";

test("the default app synthesises its stack with the Repo tag", () => {
  const assembly = createApp().synth();
  const stack = assembly.getStackByName(STACK_NAME);

  expect(stack.tags).toEqual({ Repo: "schuettc/research-in-a-box" });
});
