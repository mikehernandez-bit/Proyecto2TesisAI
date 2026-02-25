import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

const venvPython =
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const pythonBin = process.env.PYTHON_BIN ?? (existsSync(venvPython) ? venvPython : "python");

export default defineConfig({
  testDir: "./e2e/tests",
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8001",
    headless: true,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "on-first-retry",
  },
  webServer: {
    command: `${pythonBin} -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
    url: "http://127.0.0.1:8001",
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
    env: {
      GEMINI_API_KEY: "",
      N8N_WEBHOOK_URL: "",
    },
  },
});
