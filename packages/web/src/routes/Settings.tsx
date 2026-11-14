import { useEffect, useState } from "react";
import {
  ApiRefused,
  getPolicy,
  listCurators,
  savePolicy,
  type Curator,
  type ReviewPolicy,
  type Rule,
} from "../api";
import { accessLabel } from "../labels";
import { PageHeading, useTitle } from "../page";
import { usePeople } from "../People";

/** What the form reads from the contract's JSON Schema: each field's values and defaults. */
interface PolicySchema {
  required: boolean;
  staleDays: number;
  kinds: string[];
  access: string[];
  outcomes: string[];
  description: string | null;
}

interface JsonSchema {
  default?: unknown;
  enum?: string[];
  anyOf?: JsonSchema[];
  items?: JsonSchema;
  description?: string;
  properties?: Record<string, JsonSchema>;
}

/** An enum's values, through `anyOf` (a nullable field) and `items` (a list). */
function values(schema: JsonSchema | undefined): string[] {
  if (!schema) return [];
  if (schema.enum) return schema.enum;
  for (const part of schema.anyOf ?? []) {
    const found = values(part);
    if (found.length) return found;
  }
  return values(schema.items);
}

/** The ReviewPolicy and Rule models of the contract's JSON Schema, read on the settings page. */
async function loadSchema(): Promise<PolicySchema> {
  const contract = (await import("../schema/archive-contract.schema.json")) as {
    $defs: Record<string, JsonSchema>;
  };
  const policy = contract.$defs.ReviewPolicy?.properties ?? {};
  const rule = contract.$defs.Rule?.properties ?? {};
  return {
    required: policy.required?.default !== false,
    staleDays: typeof policy.staleDays?.default === "number" ? policy.staleDays.default : 14,
    kinds: values(rule.kind),
    access: values(rule.access),
    outcomes: values(rule.outcome),
    description: contract.$defs.ReviewPolicy?.description ?? null,
  };
}

const KIND_WORDS: Record<string, string> = {
  "new-dataset": "New dataset",
  "new-version": "New version",
};
const OUTCOME_WORDS: Record<string, string> = {
  skip: "Publish without review",
  one: "One curator",
  two: "Two curators",
};

/** A comma-separated list as the strings in it. */
const words = (text: string) =>
  text
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean);

function RuleFields({
  rule,
  index,
  count,
  schema,
  curators,
  change,
  move,
  remove,
}: {
  rule: Rule;
  index: number;
  count: number;
  schema: PolicySchema;
  curators: Curator[];
  change: (rule: Rule) => void;
  move: (by: number) => void;
  remove: () => void;
}) {
  const n = index + 1;
  const submitters = rule.submitters ?? [];
  const people = [
    ...curators.map((curator) => curator.sub),
    ...submitters.filter((sub) => sub !== "curators" && !curators.some((c) => c.sub === sub)),
  ];
  const email = usePeople(submitters.filter((sub) => sub !== "curators"));
  const nameOf = (sub: string) => curators.find((c) => c.sub === sub)?.email ?? email(sub);
  const [themes, setThemes] = useState((rule.themes ?? []).join(", "));

  function toggle(list: string[] | null | undefined, value: string, on: boolean): string[] | null {
    const next = on ? [...(list ?? []), value] : (list ?? []).filter((item) => item !== value);
    return next.length ? next : null;
  }

  return (
    <fieldset className="rule" aria-label={`Rule ${n}`}>
      <legend>Rule {n}</legend>
      <div className="rule-grid">
        <fieldset className="choices" aria-label="Submitters">
          <legend>Submitted by</legend>
          <label className="facet">
            <input
              type="checkbox"
              checked={submitters.includes("curators")}
              onChange={(event) =>
                change({
                  ...rule,
                  submitters: toggle(submitters, "curators", event.target.checked),
                })
              }
            />
            Any curator
          </label>
          {people.map((sub) => (
            <label key={sub} className="facet">
              <input
                type="checkbox"
                checked={submitters.includes(sub)}
                onChange={(event) =>
                  change({ ...rule, submitters: toggle(submitters, sub, event.target.checked) })
                }
              />
              {nameOf(sub)}
            </label>
          ))}
          <p className="hint">None ticked: anyone.</p>
        </fieldset>
        <fieldset className="choices" aria-label="Access">
          <legend>Access</legend>
          {schema.access.map((level) => (
            <label key={level} className="facet">
              <input
                type="checkbox"
                checked={(rule.access ?? []).includes(level as never)}
                onChange={(event) =>
                  change({
                    ...rule,
                    access: toggle(rule.access, level, event.target.checked) as Rule["access"],
                  })
                }
              />
              {accessLabel(level)}
            </label>
          ))}
          <p className="hint">None ticked: any access.</p>
        </fieldset>
        <div className="rule-fields">
          <label className="field">
            Kind
            <select
              value={rule.kind ?? ""}
              onChange={(event) =>
                change({ ...rule, kind: (event.target.value || null) as Rule["kind"] })
              }
            >
              <option value="">Any</option>
              {schema.kinds.map((kind) => (
                <option key={kind} value={kind}>
                  {KIND_WORDS[kind] ?? kind}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>
              Themes <span className="muted">(comma-separated; none: any)</span>
            </span>
            <input
              type="text"
              value={themes}
              onChange={(event) => {
                setThemes(event.target.value);
                const list = words(event.target.value);
                change({ ...rule, themes: list.length ? list : null });
              }}
            />
          </label>
          <label className="field">
            Outcome
            <select
              value={rule.outcome}
              onChange={(event) =>
                change({ ...rule, outcome: event.target.value as Rule["outcome"] })
              }
            >
              {schema.outcomes.map((outcome) => (
                <option key={outcome} value={outcome}>
                  {OUTCOME_WORDS[outcome] ?? outcome}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <p className="actions rule-actions">
        <button type="button" disabled={index === 0} onClick={() => move(-1)}>
          Move up <span className="visually-hidden">rule {n}</span>
        </button>
        <button type="button" disabled={index === count - 1} onClick={() => move(1)}>
          Move down <span className="visually-hidden">rule {n}</span>
        </button>
        <button type="button" onClick={remove}>
          Remove <span className="visually-hidden">rule {n}</span>
        </button>
      </p>
    </fieldset>
  );
}

type Loaded = { policy: ReviewPolicy; curators: Curator[]; schema: PolicySchema };

function PolicyForm({ loaded }: { loaded: Loaded }) {
  const { schema, curators } = loaded;
  const [policy, setPolicy] = useState<ReviewPolicy>(loaded.policy);
  // Each rule keeps a key of its own, so moving one moves its fields with it.
  const [keys, setKeys] = useState(() => (loaded.policy.rules ?? []).map((_, n) => n));
  const [nextKey, setNextKey] = useState((loaded.policy.rules ?? []).length);
  const [reminders, setReminders] = useState<string | null>(null);
  const [newTheme, setNewTheme] = useState("");
  const [saving, setSaving] = useState(false);
  const [said, setSaid] = useState<{ ok: boolean; text: string } | null>(null);
  const rules = policy.rules ?? [];
  const required = policy.required ?? schema.required;
  const staleDays = policy.staleDays ?? schema.staleDays;

  function setRules(next: Rule[], nextKeys: number[]) {
    setPolicy({ ...policy, rules: next });
    setKeys(nextKeys);
  }

  function move(index: number, by: number) {
    const next = [...rules];
    const order = [...keys];
    [next[index], next[index + by]] = [next[index + by]!, next[index]!];
    [order[index], order[index + by]] = [order[index + by]!, order[index]!];
    setRules(next, order);
  }

  function addRule() {
    const outcome = (
      schema.outcomes.includes("one") ? "one" : schema.outcomes[0]
    ) as Rule["outcome"];
    setRules(
      [...rules, { submitters: null, kind: null, access: null, themes: null, outcome }],
      [...keys, nextKey],
    );
    setNextKey(nextKey + 1);
  }

  function setReviewers(theme: string, subs: string[] | null) {
    const next = { ...(policy.reviewers ?? {}) };
    if (subs === null) delete next[theme];
    else next[theme] = subs;
    setPolicy({ ...policy, reviewers: next });
  }

  function save() {
    let body = policy;
    if (reminders !== null) {
      const days = words(reminders);
      if (days.some((day) => !/^\d+$/.test(day))) {
        setSaid({ ok: false, text: "Remind on days takes whole numbers of days, like 3, 7." });
        return;
      }
      body = { ...policy, reminders: days.map(Number) };
    }
    setSaving(true);
    setSaid(null);
    savePolicy(body).then(
      (stored) => {
        setSaving(false);
        setPolicy(stored);
        setReminders(null);
        setSaid({
          ok: true,
          text: "Saved. It applies to submissions entering review from now on; those already waiting keep the policy they entered with.",
        });
      },
      (error: unknown) => {
        setSaving(false);
        setSaid({
          ok: false,
          text:
            error instanceof ApiRefused
              ? (error.reason ?? error.message)
              : "The archive can't be reached right now.",
        });
      },
    );
  }

  const reviewers = policy.reviewers ?? {};
  return (
    <form
      className="policy"
      onSubmit={(event) => {
        event.preventDefault();
        save();
      }}
    >
      <section className="block" aria-labelledby="review-heading">
        <h2 id="review-heading">Review</h2>
        <label className="switch">
          <input
            type="checkbox"
            role="switch"
            checked={required}
            onChange={(event) => setPolicy({ ...policy, required: event.target.checked })}
          />
          Review required
        </label>
        <p className="hint">
          With no rule matching, a submission{" "}
          {required ? "needs one curator" : "is published without review"}.
        </p>
      </section>
      <section className="block" aria-labelledby="rules-heading">
        <h2 id="rules-heading">Rules</h2>
        <p className="hint">Tried in order; the first that matches decides.</p>
        {rules.length === 0 && <p className="muted">No rules.</p>}
        {rules.map((rule, index) => (
          <RuleFields
            key={keys[index]}
            rule={rule}
            index={index}
            count={rules.length}
            schema={schema}
            curators={curators}
            change={(next) => setRules(rules.with(index, next), keys)}
            move={(by) => move(index, by)}
            remove={() =>
              setRules(
                rules.filter((_, n) => n !== index),
                keys.filter((_, n) => n !== index),
              )
            }
          />
        ))}
        <p className="actions">
          <button type="button" onClick={addRule}>
            Add a rule
          </button>
        </p>
      </section>
      <section className="block" aria-labelledby="reviewers-heading">
        <h2 id="reviewers-heading">Named reviewers</h2>
        <p className="hint">The curators asked first for a dataset with each theme.</p>
        {Object.entries(reviewers).map(([theme, subs]) => (
          <fieldset key={theme} className="choices theme" aria-label={`Reviewers for ${theme}`}>
            <legend>{theme}</legend>
            {curators.map((curator) => (
              <label key={curator.sub} className="facet">
                <input
                  type="checkbox"
                  checked={subs.includes(curator.sub)}
                  onChange={(event) =>
                    setReviewers(
                      theme,
                      event.target.checked
                        ? [...subs, curator.sub]
                        : subs.filter((sub) => sub !== curator.sub),
                    )
                  }
                />
                {curator.email}
              </label>
            ))}
            <p className="actions">
              <button type="button" onClick={() => setReviewers(theme, null)}>
                Remove <span className="visually-hidden">the theme {theme}</span>
              </button>
            </p>
          </fieldset>
        ))}
        <div className="add-theme">
          <label className="field">
            New theme
            <input
              type="text"
              value={newTheme}
              onChange={(event) => setNewTheme(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={!newTheme.trim() || newTheme.trim() in reviewers}
            onClick={() => {
              setReviewers(newTheme.trim(), []);
              setNewTheme("");
            }}
          >
            Add the theme
          </button>
        </div>
      </section>
      <section className="block" aria-labelledby="timing-heading">
        <h2 id="timing-heading">Reminders</h2>
        <div className="timing">
          <label className="field">
            <span>
              Remind on days <span className="muted">(comma-separated)</span>
            </span>
            <input
              type="text"
              inputMode="numeric"
              value={reminders ?? (policy.reminders ?? []).join(", ")}
              onChange={(event) => setReminders(event.target.value)}
            />
          </label>
          <label className="field">
            Stale after (days)
            <input
              type="number"
              min={1}
              value={staleDays}
              onChange={(event) => setPolicy({ ...policy, staleDays: Number(event.target.value) })}
            />
          </label>
        </div>
        <p className="hint">Each reminder comes before the stale mark.</p>
      </section>
      <div className="save-row">
        <button type="submit" className="primary" disabled={saving}>
          Save the policy
        </button>
        {said &&
          (said.ok ? (
            <p role="status" className="saved">
              {said.text}
            </p>
          ) : (
            <p role="alert" className="problem">
              {said.text}
            </p>
          ))}
      </div>
    </form>
  );
}

/** `/settings`: the admin's review policy, as a form saved whole. */
export function Settings() {
  useTitle("Settings");
  const [loaded, setLoaded] = useState<Loaded | "failed" | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    Promise.all([getPolicy(), listCurators(), loadSchema()]).then(
      ([policy, curators, schema]) => current && setLoaded({ policy, curators, schema }),
      () => current && setLoaded("failed"),
    );
    return () => {
      current = false;
    };
  }, [attempt]);

  return (
    <>
      <PageHeading>Settings</PageHeading>
      <p className="lede">
        The review policy: which submissions a curator reviews, how many, and when they are
        reminded.
      </p>
      {loaded === "failed" ? (
        <>
          <p role="alert">The policy can't be loaded right now.</p>
          <p className="actions">
            <button type="button" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </p>
        </>
      ) : loaded === null ? (
        <p role="status" className="muted">
          Loading the policy…
        </p>
      ) : (
        <PolicyForm loaded={loaded} />
      )}
    </>
  );
}
