import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";

const chromium =
  process.env.PT_CHROMIUM_PATH ??
  (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined);

const local = process.env.PT_E2E_API === "1";
export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: local ? "http://127.0.0.1:5173" : "http://127.0.0.1:4173",
    launchOptions: { executablePath: chromium },
  },
  webServer: local
    ? undefined
    : {
        command: "npm run preview -- --port 4173 --strictPort",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: false,
      },
  workers: 2,
});
