import { useEffect, useSyncExternalStore } from "react";
import { lookupPeople } from "./api";
import { groups, signedInSub, subscribe } from "./auth";

const BATCH = 50;

/** Each id looked up: its email, or null when the pool doesn't know it. */
const known = new Map<string, string | null>();
const asked = new Set<string>();
let queued: string[] = [];
let version = 0;
const listeners = new Set<() => void>();

function changed(): void {
  version += 1;
  for (const listener of listeners) listener();
}

function listen(listener: () => void): () => void {
  listeners.add(listener);
  const stop = subscribe(listener);
  return () => {
    listeners.delete(listener);
    stop();
  };
}

/** Forget every email looked up (for tests, and a reader who signs out). */
export function forgetPeople(): void {
  known.clear();
  asked.clear();
  queued = [];
  changed();
}

/** Ask for every id queued in this tick, 50 to a call. */
function flush(): void {
  const subs = queued;
  queued = [];
  for (let start = 0; start < subs.length; start += BATCH) {
    const batch = subs.slice(start, start + BATCH);
    lookupPeople(batch).then(
      (answer) => {
        for (const sub of batch) known.set(sub, answer.people[sub]?.email ?? null);
        changed();
      },
      // A failed lookup leaves the ids unasked, so the next page that needs them asks again.
      () => {
        for (const sub of batch) asked.delete(sub);
      },
    );
  }
}

function want(subs: string[]): void {
  const fresh = subs.filter((sub) => sub !== "pipeline" && !asked.has(sub));
  if (fresh.length === 0) return;
  for (const sub of fresh) asked.add(sub);
  if (queued.length === 0) queueMicrotask(flush);
  queued.push(...fresh);
}

/** Whether the reader may look people up: `/api/people` answers curators and admins. */
function canLookUp(): boolean {
  const mine = groups();
  return mine.includes("curator") || mine.includes("admin");
}

/**
 * Names for user ids: "you" for the reader, "the archive" for the pipeline, an email once
 * looked up. Every id the page asks for in one render goes to `/api/people` together, and is
 * kept for the rest of the visit. A reader who can't look people up (a contributor) sees
 * "a curator" for anyone else, since only curators act on their submissions.
 */
export function usePeople(subs: readonly string[]): (sub: string) => string {
  useSyncExternalStore(listen, () => version);
  const me = signedInSub();
  const lookUp = canLookUp();
  const key = subs.join(" ");

  useEffect(() => {
    if (lookUp) want(key.split(" ").filter((sub) => sub && sub !== me));
  }, [key, lookUp, me]);

  return (sub: string) => {
    if (sub === me) return "you";
    if (sub === "pipeline") return "the archive";
    if (!lookUp) return "a curator";
    const email = known.get(sub);
    if (email === undefined) return "…";
    return email ?? "someone";
  };
}
