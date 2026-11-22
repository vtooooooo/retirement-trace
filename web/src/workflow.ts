import type { Case } from "./types";

export type Role = "analyst" | "senior" | "benefits" | "auditor" | "admin";

const byState: Record<string, ReadonlyArray<readonly [Role, string]>> = {
  Detected: [["analyst", "triage"]],
  Triaged: [["analyst", "investigate"]],
  "Awaiting evidence": [
    ["analyst", "investigate"],
    ["analyst", "request_review"],
  ],
  "Under investigation": [
    ["analyst", "await_evidence"],
    ["analyst", "request_review"],
  ],
  "Pending senior review": [
    ["senior", "approve_review"],
    ["senior", "approve_identity"],
    ["senior", "reject_identity"],
  ],
  "Pending benefits review": [["benefits", "resolve"]],
  Resolved: [
    ["benefits", "close"],
    ["analyst", "reopen"],
  ],
  Closed: [["analyst", "reopen"]],
  Reopened: [["analyst", "investigate"]],
};

export function availableDecisions(
  state: string,
  issue: string,
  role?: Role,
): string[] {
  const options = (byState[state] ?? []).flatMap(([allowed, action]) =>
    allowed === role && (action !== "approve_review" || issue !== "identifier")
      ? [action]
      : [],
  );
  if (
    (role === "analyst" || role === "senior") &&
    !["Resolved", "Closed"].includes(state)
  ) {
    options.push("note", "assign", "record_action", "attach");
  }
  return options;
}

export function prioritize(cases: Case[]) {
  return cases
    .filter((c) => !["Resolved", "Closed"].includes(c.state))
    .sort(
      (a, b) =>
        Number(b.alert.severity === "high") -
          Number(a.alert.severity === "high") ||
        a.created.localeCompare(b.created) ||
        a.id.localeCompare(b.id),
    );
}
