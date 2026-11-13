import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const user = JSON.parse(
  readFileSync(new URL("../../.local/dev-user.json", import.meta.url), "utf8"),
);
const outputs = JSON.parse(
  readFileSync(
    new URL("../../.local/floci-outputs.json", import.meta.url),
    "utf8",
  ),
);

async function login(page, password = user.password) {
  await page.getByLabel("ユーザー名", { exact: true }).fill(user.username);
  await page.getByLabel("パスワード", { exact: true }).fill(password);
  await page.getByRole("button", { name: "ログイン", exact: true }).click();
}

async function accessToken(page) {
  return page.evaluate(
    async ({ clientId, username, password }) => {
      const r = await fetch("/auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-amz-json-1.1",
          "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
        },
        body: JSON.stringify({
          ClientId: clientId,
          AuthFlow: "USER_PASSWORD_AUTH",
          AuthParameters: { USERNAME: username, PASSWORD: password },
        }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error("Local sign-in failed");
      return data.AuthenticationResult.AccessToken;
    },
    {
      clientId: outputs.CognitoClientId,
      username: user.username,
      password: user.password,
    },
  );
}

test("static HTTPS app: sign-in, real cross-origin inference, logout, no persisted token", async ({
  page,
}) => {
  await page.goto("/");
  await page.screenshot({
    path: "../.local/security-login.png",
    fullPage: true,
  });
  await login(page, "incorrect-local-password");
  await expect(page.getByRole("alert")).toHaveText("ログインできません。");
  await login(page);
  await expect(page.getByLabel("文章", { exact: true })).toBeVisible();
  await page
    .getByLabel("文章", { exact: true })
    .fill("今日はとても楽しかった！");
  const response = page.waitForResponse(
    (r) =>
      r.url() === "https://localhost:9443/predict/lora" &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "分析", exact: true }).click();
  const result = await response;
  expect(result.status()).toBe(200);
  expect(result.headers()["access-control-allow-origin"]).toBe(
    "https://localhost:8443",
  );
  for (const model of ["LoRA", "Full FT"]) {
    const card = page.getByRole("region", { name: `${model}の結果` });
    await expect(card.locator(".prediction")).toBeVisible({ timeout: 90000 });
    await expect(card.locator(".prob-row")).toHaveCount(5);
  }
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
  await page.screenshot({
    path: "../.local/security-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "../.local/security-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "ログアウト", exact: true }).click();
  await expect(page.getByLabel("パスワード", { exact: true })).toHaveValue("");
  await login(page);
  await page.reload();
  await expect(page.getByLabel("パスワード", { exact: true })).toBeVisible();
});

test("browser enforces CORS for disallowed origins even with a valid JWT", async ({
  page,
}) => {
  await page.goto("/");
  const token = await accessToken(page);
  const fetchResult = async () =>
    page.evaluate(async (token) => {
      try {
        const r = await fetch("https://localhost:9443/predict/lora", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ text: "明日は月曜日です。" }),
        });
        return { readable: true, status: r.status };
      } catch {
        return { readable: false };
      }
    }, token);
  expect(await fetchResult()).toEqual({ readable: true, status: 200 });
  await page.goto("https://localhost:8445");
  expect(await fetchResult()).toEqual({ readable: false });
  await page.goto("https://app.wrime.test:8443");
  await expect(page.getByRole("heading", { name: "感情分析" })).toBeVisible();
  expect(await fetchResult()).toEqual({ readable: false });
});
