import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

const chrome =
  process.env.PT_CHROMIUM_PATH ??
  (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined);
const baseURL = process.env.PT_E2E_FRONTEND_URL ?? process.env.PT_E2E_LOCAL_URL ?? "http://127.0.0.1:5173";
if (process.env.PT_E2E_FRONTEND_URL && new URL(baseURL).protocol !== "https:") {
  throw new Error("Hosted smoke tests require an HTTPS frontend");
}
export default defineConfig({
  testDir: "./tests",
  use: { baseURL, launchOptions: { executablePath: chrome } },
  workers: 1,
  timeout: 90_000,
});
