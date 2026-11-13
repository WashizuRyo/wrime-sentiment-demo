import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
const pin = readFileSync(
  new URL("../.local/security/cert-spki.txt", import.meta.url),
  "utf8",
).trim();
const browser = await chromium.launch({
  headless: false,
  args: [`--ignore-certificate-errors-spki-list=${pin}`],
});
const page = await browser.newPage();
await page.goto("https://localhost:8443");
console.log("Local HTTPS browser opened. Close the window to finish.");
await new Promise((resolve) => browser.on("disconnected", resolve));
