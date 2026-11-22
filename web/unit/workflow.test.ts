import { test } from "node:test";
import assert from "node:assert/strict";
import { availableDecisions, prioritize } from "../src/workflow.ts";
import type { Case } from "../src/types.ts";

test("only the appointed role can advance the case", () => {
  assert.deepEqual(
    availableDecisions("Pending benefits review", "unpaid", "benefits"),
    ["resolve"],
  );
  assert.deepEqual(
    availableDecisions("Pending benefits review", "unpaid", "auditor"),
    [],
  );
  assert.deepEqual(availableDecisions("Closed", "unpaid", "analyst"), [
    "reopen",
  ]);
  assert.deepEqual(availableDecisions("Detected", "unpaid"), []);
});

test("identifier conflicts require a case-specific candidate decision", () => {
  const actions = availableDecisions(
    "Pending senior review",
    "identifier",
    "senior",
  );
  assert.ok(actions.includes("approve_identity"));
  assert.ok(!actions.includes("approve_review"));
});

test("the priority queue hides closed cases and orders high priority by age", () => {
  const row = (
    id: string,
    severity: string,
    created: string,
    state = "Detected",
  ) => ({ id, state, created, alert: { severity } }) as Case;
  const rows = [
    row("A", "medium", "2026-01-01"),
    row("B", "high", "2026-01-02"),
    row("C", "high", "2026-01-01"),
    row("D", "high", "2026-01-01", "Closed"),
  ];
  assert.deepEqual(
    prioritize(rows).map((r) => r.id),
    ["C", "B", "A"],
  );
  assert.deepEqual(
    rows.map((r) => r.id),
    ["A", "B", "C", "D"],
  );
});
