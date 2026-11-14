import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import type { ReviewPolicy } from "../api";
import { forgetPeople } from "../People";
import { Settings } from "./Settings";

vi.mock("../auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../auth")>()),
  apiToken: vi.fn(() => "token"),
  signedInSub: vi.fn(() => "adm-1"),
  groups: vi.fn(() => ADMIN),
}));
const ADMIN = ["admin", "curator"];

const STORED: ReviewPolicy = {
  required: true,
  rules: [
    { submitters: ["curators"], kind: null, access: null, themes: null, outcome: "skip" },
    {
      submitters: null,
      kind: "new-version",
      access: ["restricted"],
      themes: ["hydrology"],
      outcome: "two",
    },
  ],
  reviewers: { hydrology: ["cur-1"] },
  reminders: [3, 7],
  staleDays: 14,
};

let fetchMock: Mock;
let saved: unknown[];

beforeEach(() => {
  forgetPeople();
  saved = [];
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "https://site").pathname;
    if (path === "/api/curators") {
      return Response.json([
        { sub: "cur-1", email: "curator@example.org" },
        { sub: "cur-2", email: "second@example.org" },
      ]);
    }
    if (path === "/api/people") return Response.json({ people: {} });
    if (path === "/api/submissions/policy" && init?.method === "PUT") {
      const body = JSON.parse(String(init.body)) as ReviewPolicy;
      saved.push(body);
      if ((body.reminders ?? []).some((day) => day >= body.staleDays)) {
        return Response.json(
          { error: "invalid policy: reminders must each come before staleDays" },
          { status: 400 },
        );
      }
      return Response.json(body);
    }
    if (path === "/api/submissions/policy") return Response.json(STORED);
    return Response.json({}, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderSettings() {
  return render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>,
  );
}

const save = () => fireEvent.click(screen.getByRole("button", { name: "Save the policy" }));

test("the form loads the stored policy and saves it unchanged", async () => {
  renderSettings();
  await screen.findByRole("group", { name: "Rule 1" });

  expect(
    (screen.getByRole("switch", { name: "Review required" }) as HTMLInputElement).checked,
  ).toBe(true);
  expect((screen.getByLabelText("Stale after (days)") as HTMLInputElement).value).toBe("14");
  expect((screen.getByLabelText(/Remind on days/) as HTMLInputElement).value).toBe("3, 7");
  save();

  await waitFor(() => expect(saved).toEqual([STORED]));
  expect((await screen.findByRole("status")).textContent).toMatch(/entering review from now on/);
});

test("reordering the rules changes the saved order", async () => {
  renderSettings();
  const first = await screen.findByRole("group", { name: "Rule 1" });

  fireEvent.click(within(first).getByRole("button", { name: "Move down rule 1" }));
  save();

  await waitFor(() => expect(saved).toHaveLength(1));
  expect((saved[0] as ReviewPolicy).rules?.map((rule) => rule.outcome)).toEqual(["two", "skip"]);
});

test("a rule's outcome, kind and access offer the schema's values", async () => {
  renderSettings();
  const second = await screen.findByRole("group", { name: "Rule 2" });

  const outcome = within(second).getByLabelText("Outcome") as HTMLSelectElement;
  expect([...outcome.options].map((option) => option.value)).toEqual(["skip", "one", "two"]);
  const kind = within(second).getByLabelText("Kind") as HTMLSelectElement;
  expect([...kind.options].map((option) => option.value)).toEqual([
    "",
    "new-dataset",
    "new-version",
  ]);
  const access = within(second).getByRole("group", { name: "Access" });
  expect(within(access).getAllByRole("checkbox")).toHaveLength(4);
  fireEvent.change(outcome, { target: { value: "one" } });
  fireEvent.click(within(access).getByRole("checkbox", { name: "Open" }));
  save();

  await waitFor(() => expect(saved).toHaveLength(1));
  const rule = (saved[0] as ReviewPolicy).rules?.[1];
  expect(rule?.outcome).toBe("one");
  expect(rule?.access).toEqual(["restricted", "open"]);
});

test("a reminder past the stale mark shows the API's message", async () => {
  renderSettings();
  await screen.findByRole("group", { name: "Rule 1" });

  fireEvent.change(screen.getByLabelText(/Remind on days/), { target: { value: "3, 20" } });
  save();

  expect((await screen.findByRole("alert")).textContent).toContain(
    "invalid policy: reminders must each come before staleDays",
  );
  expect((saved[0] as ReviewPolicy).reminders).toEqual([3, 20]);
});

test("the reviewer picker lists the curators by email", async () => {
  renderSettings();
  const theme = await screen.findByRole("group", { name: "Reviewers for hydrology" });

  const boxes = within(theme).getAllByRole("checkbox") as HTMLInputElement[];
  expect(boxes.map((box) => box.labels?.[0]?.textContent)).toEqual([
    "curator@example.org",
    "second@example.org",
  ]);
  expect(boxes.map((box) => box.checked)).toEqual([true, false]);
  fireEvent.click(boxes[1]!);
  save();

  await waitFor(() => expect(saved).toHaveLength(1));
  expect((saved[0] as ReviewPolicy).reviewers).toEqual({ hydrology: ["cur-1", "cur-2"] });
});

test("adding and removing a rule", async () => {
  renderSettings();
  await screen.findByRole("group", { name: "Rule 1" });

  fireEvent.click(screen.getByRole("button", { name: "Add a rule" }));
  fireEvent.click(
    within(screen.getByRole("group", { name: "Rule 1" })).getByRole("button", {
      name: "Remove rule 1",
    }),
  );
  save();

  await waitFor(() => expect(saved).toHaveLength(1));
  expect((saved[0] as ReviewPolicy).rules?.map((rule) => rule.outcome)).toEqual(["two", "one"]);
});

test("an axe check of the settings form finds no violations", async () => {
  const { container } = renderSettings();
  await screen.findByRole("group", { name: "Reviewers for hydrology" });

  expect((await axe.run(container)).violations).toEqual([]);
});
