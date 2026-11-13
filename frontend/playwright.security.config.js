import { defineConfig } from "@playwright/test";
import { readFileSync } from "node:fs";

const pin = readFileSync(
  new URL("../.local/security/cert-spki.txt", import.meta.url),
  "utf8",
).trim();
export default defineConfig({
  testDir: "./security-tests",
  timeout: 120000,
  workers: 1,
  use: {
    baseURL: "https://localhost:8443",
    browserName: "chromium",
    // Trust only this local leaf's public key, scoped to this browser process.
    // Do not use ignoreHTTPSErrors or change the OS certificate store.
    launchOptions: {
      args: [
        `--ignore-certificate-errors-spki-list=${pin}`,
        "--host-resolver-rules=MAP app.wrime.test 127.0.0.1,MAP api.wrime.test 127.0.0.1",
      ],
    },
  },
});
