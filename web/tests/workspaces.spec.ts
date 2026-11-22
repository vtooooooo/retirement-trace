import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";

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

test("public workspaces, evidence journey and export", async ({ page }) => {
  test.skip(process.env.PT_E2E_API === "1");
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Priority work queue" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search cases and participants" })
    .fill("conflicting identifiers");
  await page.getByRole("button", { name: /RC-1053/ }).click();
  await expect(page.getByText("Decision recording is disabled")).toBeVisible();
  await page.getByRole("button", { name: "Compare identities" }).click();
  await expect(
    page.getByRole("heading", { name: "Conflicting features" }),
  ).toBeVisible();
  await page.getByLabel("Candidate pair").selectOption({
    label:
      (await page
        .getByLabel("Candidate pair")
        .locator("option")
        .first()
        .textContent()) ?? "",
  });
  const dir = process.env.PT_SCREENSHOTS;
  if (dir) await mkdir(dir, { recursive: true });
  for (const [i, [nav, heading]] of workspaces.entries()) {
    await page.getByRole("navigation").getByRole("link", { name: nav }).click();
    await expect(
      page.getByRole("heading", { level: 1, name: heading }),
    ).toBeVisible();
    await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
    if (dir)
      await page.screenshot({
        path: join(
          dir,
          String(i + 1).padStart(2, "0") +
            "-" +
            nav.toLowerCase().replace(/[^a-z]+/g, "-") +
            ".png",
        ),
        fullPage: i !== 2 && i !== 5,
      });
  }
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export audit report" }).click();
  expect((await downloadPromise).suggestedFilename()).toBe(
    "RC-1053-synthetic-audit.json",
  );
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Evidence Graph" })
    .click();
  await page
    .getByRole("button", { name: /Contradicted/ })
    .first()
    .click();
  await page.getByRole("button", { name: "Open source record" }).click();
  await expect(page.getByText("Validation", { exact: true })).toBeVisible();
  await page.getByLabel("Evidence type").selectOption("correspondence");
  await expect(
    page.getByRole("button", { name: /Annual statement/ }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Case Workflow" })
    .click();
  await page.getByLabel("Filter by status").selectOption("Detected");
  await expect(
    page.getByRole("row").filter({ hasText: "Triaged" }),
  ).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("tablet navigation, guided walkthrough and layout", async ({ page }) => {
  test.skip(process.env.PT_E2E_API === "1");
  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Priority work queue" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open demo walkthrough" }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      level: 2,
      name: "Obligation without payment record",
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Investigation Intelligence" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Recommended investigation actions" }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    768,
  );
});

test("local operator and independent reviewer record an auditable decision", async ({
  page,
}) => {
  test.skip(process.env.PT_E2E_API !== "1");
  await page.goto("/");
  async function connect(credential: string) {
    await page.getByRole("button", { name: "Connect local API" }).click();
    await page.getByLabel("Local API credential").fill(credential);
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.getByText("Authenticated session")).toBeVisible();
  }
  await connect("browser-analyst");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Benefit Discrepancies" })
    .click();
  await page
    .getByRole("combobox", { name: "Select case" })
    .selectOption("RC-1047");
  await expect(
    page.getByRole("heading", {
      name: "Obligation without payment record",
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Explore evidence" }).click();
  await expect(
    page.getByRole("heading", { name: "Case evidence graph" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Search cases and participants" })
    .fill("RC-1053");
  await page.getByRole("button", { name: /RC-1053/ }).click();
  await page.getByRole("button", { name: "Compare identities" }).click();
  await expect(
    page.getByRole("heading", { name: "Conflicting features" }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Investigation Intelligence" })
    .click();
  await expect(
    page.getByText("Modeled information gain").first(),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Case Workflow" })
    .click();
  await page
    .getByRole("combobox", { name: "Decision", exact: true })
    .selectOption("request_review");
  await page
    .getByLabel("Decision rationale")
    .fill("Request independent review of the identifier conflict");
  await page
    .getByRole("button", { name: "Record decision", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Decision recorded");
  await page.getByRole("button", { name: "Connect local API" }).click();
  await page.getByRole("button", { name: "Disconnect" }).click();
  await connect("browser-senior");
  await page
    .getByRole("combobox", { name: "Decision", exact: true })
    .selectOption("approve_identity");
  const options = page.getByRole("combobox", {
    name: "Reference",
    exact: true,
  });
  await options.selectOption({ index: 1 });
  await page
    .getByLabel("Decision rationale")
    .fill("Reviewed the synthetic supporting records");
  await page
    .getByRole("button", { name: "Record decision", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Decision recorded");
  await page.getByRole("button", { name: "Audit report", exact: true }).click();
  await expect(
    page.getByText("Reviewed the synthetic supporting records"),
  ).toBeVisible();
});
