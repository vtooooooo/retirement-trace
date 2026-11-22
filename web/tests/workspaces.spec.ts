import { expect, test, type Page } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";

const roles = ["analyst", "senior", "benefits", "auditor"] as const;
type Role = (typeof roles)[number];
const workspaces = [
  ["Command Center", "Retirement Operations"],
  ["Identity Resolution", "Participant Identity Resolution"],
  ["Benefit Discrepancies", "Benefit Discrepancies"],
  ["Evidence Graph", "Participant Evidence Graph"],
  ["Investigation Intelligence", "Investigation Intelligence"],
  ["Case Workflow", "Case Resolution Workflow"],
  ["Model & Operations", "Model & Operational Analytics"],
  ["Audit & Governance", "Audit & Governance"],
];

async function signIn(page: Page, role: Role) {
  const prefix = "PT_E2E_" + role.toUpperCase();
  const user = process.env[prefix + "_USER"];
  const password = process.env[prefix + "_PASSWORD"];
  if (!user || !password)
    throw new Error("Missing browser test credentials for " + role);
  await page.goto("/");
  await page.getByLabel("Username", { exact: true }).fill(user);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign out", exact: true }),
  ).toBeVisible();
  const response = await page.request.get("/api/v1/session");
  expect(response.ok()).toBeTruthy();
  const session = await response.json();
  expect(session.role).toBe(role);
  return session.tenant as string;
}

async function visit(page: Page, name: string) {
  await page
    .getByRole("navigation")
    .getByRole("link", { name, exact: true })
    .click();
}

async function openCase(page: Page, id: string) {
  await visit(page, "Case Workflow");
  await page.getByRole("combobox", { name: "Select case" }).selectOption(id);
}

async function decision(page: Page, action: string, note: string) {
  await page
    .getByRole("combobox", { name: "Decision", exact: true })
    .selectOption(action);
  if (action === "approve_identity") {
    await page
      .getByRole("combobox", { name: "Reference", exact: true })
      .selectOption({ index: 1 });
  }
  await page.getByLabel("Decision rationale").fill(note);
  await page
    .getByRole("button", { name: "Record decision", exact: true })
    .click();
  await expect(
    page.getByText("Decision recorded in the audit trail."),
  ).toBeVisible();
}

test("backend readiness, edge health, and protected workspace", async ({
  request,
  baseURL,
}) => {
  const backend = process.env.PT_E2E_API_URL ?? "http://127.0.0.1:8000";
  if (process.env.PT_E2E_FRONTEND_URL) {
    expect(new URL(backend).protocol).toBe("https:");
    const edge = await request.get("/api/ready", { maxRedirects: 0 });
    expect(edge.status()).toBe(200);
    expect(edge.headers()["cache-control"]).toBe("no-store");
    expect((await request.get(backend + "/api/v1/workspace")).status()).toBe(
      403,
    );
  }
  for (const path of ["/health/live", "/ready"]) {
    const result = await request.get(backend + path);
    expect(result.status()).toBe(200);
    expect(await result.json()).toEqual({ status: "ok" });
  }
  const workspace = await request.get("/api/v1/workspace", {
    headers: { Origin: baseURL! },
  });
  expect(workspace.status()).toBe(401);
});

test("workspaces, database participant search, audit download, reload, and sign-out", async ({
  page,
  context,
}) => {
  await signIn(page, "analyst");
  const cookies = await context.cookies();
  const cookie = cookies.find(
    (c) =>
      c.name ===
      (process.env.PT_E2E_FRONTEND_URL ? "__Host-pt_session" : "pt_session"),
  );
  expect(cookie?.httpOnly).toBe(true);
  if (process.env.PT_E2E_FRONTEND_URL) expect(cookie?.secure).toBe(true);
  const participant = page.getByRole("textbox", {
    name: "Search cases and participants",
  });
  const lookup = page.waitForResponse(
    (response) => response.url().includes("/participants?") && response.ok(),
  );
  await participant.fill("PT-10002");
  await lookup;
  await page.getByRole("button", { name: /PT-10002/ }).click();
  await expect(page.getByText("No investigation case is linked")).toBeVisible();
  await page.getByRole("button", { name: "Close participant" }).click();

  await openCase(page, "RC-1053");
  for (const [nav, heading] of workspaces) {
    await visit(page, nav);
    await expect(
      page.getByRole("heading", { level: 1, name: heading }),
    ).toBeVisible();
  }
  await visit(page, "Evidence Graph");
  await page.getByRole("button", { name: "Open source record" }).click();
  await expect(page.getByText("Validation", { exact: true })).toBeVisible();
  await visit(page, "Audit & Governance");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export audit report" }).click();
  expect((await download).suggestedFilename()).toBe("RC-1053-audit.json");
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Case audit trail" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  expect((await page.request.get("/api/v1/session")).status()).toBe(401);
});

test("tablet navigation and restricted auditor permissions", async ({
  page,
}) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await signIn(page, "auditor");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await visit(page, "Case Workflow");
  await expect(
    page.getByText("This role has no available decisions"),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    768,
  );
  const result = await page.request.post("/api/v1/cases/RC-1042/decisions", {
    headers: {
      Origin: new URL(page.url()).origin,
      "Idempotency-Key": crypto.randomUUID(),
    },
    data: {
      action: "note",
      note: "This auditor decision must be rejected",
      version: 1,
    },
  });
  expect([403, 409]).toContain(result.status());
});

test("four independent accounts complete and audit an identity decision", async ({
  browser,
}) => {
  const contexts = await Promise.all(roles.map(() => browser.newContext()));
  try {
    const pages = await Promise.all(
      contexts.map((context) => context.newPage()),
    );
    const tenants = await Promise.all(
      pages.map((page, index) => signIn(page, roles[index])),
    );
    expect(new Set(tenants).size).toBe(1);
    if (process.env.PT_E2E_FRONTEND_URL && process.env.PT_E2E_QA_WRITE !== "1")
      return;
    if (process.env.PT_E2E_FRONTEND_URL)
      expect(tenants.every((tenant) => tenant === "qa")).toBeTruthy();

    const [analyst, senior, benefits, auditor] = pages;
    const response = await analyst.request.get("/api/v1/workspace");
    const { cases } = (await response.json()) as {
      cases: { id: string; state: string; alert: { kind: string } }[];
    };
    const candidate = cases.find(
      (c) =>
        c.alert.kind === "identifier" &&
        [
          "Under investigation",
          "Awaiting evidence",
          "Reopened",
          "Resolved",
          "Closed",
          "Triaged",
          "Detected",
        ].includes(c.state),
    );
    expect(candidate).toBeDefined();
    const { id, state } = candidate!;
    await openCase(analyst, id);
    const note = "Browser synthetic review " + crypto.randomUUID();
    if (state === "Resolved" || state === "Closed")
      await decision(analyst, "reopen", note);
    if (state === "Detected") await decision(analyst, "triage", note);
    if (
      ["Triaged", "Detected", "Resolved", "Closed", "Reopened"].includes(state)
    )
      await decision(analyst, "investigate", note);
    await decision(analyst, "request_review", note);

    const rejected = await analyst.request.post(
      "/api/v1/cases/" + id + "/decisions",
      {
        headers: {
          Origin: new URL(analyst.url()).origin,
          "Idempotency-Key": crypto.randomUUID(),
        },
        data: {
          action: "approve_review",
          note,
          version: (
            await (await analyst.request.get("/api/v1/cases/" + id)).json()
          ).case.version,
        },
      },
    );
    expect(rejected.status()).toBe(403);

    await senior.reload();
    await openCase(senior, id);
    await decision(senior, "approve_identity", note);
    await benefits.reload();
    await openCase(benefits, id);
    await decision(benefits, "resolve", note);
    await auditor.reload();
    await openCase(auditor, id);
    await expect(
      auditor.getByText(note, { exact: true }).first(),
    ).toBeVisible();
    const artifact = process.env.PT_RESTART_PROOF;
    if (artifact)
      await writeFile(
        artifact,
        JSON.stringify({ id, note, storage: await contexts[3].storageState() }),
        { mode: 0o600 },
      );
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
  }
});

test("persisted session and audit history survive a backend process restart", async ({
  browser,
}) => {
  const artifact = process.env.PT_VERIFY_RESTART_PROOF;
  test.skip(!artifact, "Run the two-phase restart harness");
  const proof = JSON.parse(await readFile(artifact!, "utf8"));
  const context = await browser.newContext({ storageState: proof.storage });
  try {
    const page = await context.newPage();
    await page.goto("/#cases");
    await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
    await openCase(page, proof.id);
    await expect(
      page.getByText(proof.note, { exact: true }).first(),
    ).toBeVisible();
    const result = await page.request.get("/api/v1/cases/" + proof.id);
    expect((await result.json()).case.state).toBe("Resolved");
  } finally {
    await context.close();
  }
});
