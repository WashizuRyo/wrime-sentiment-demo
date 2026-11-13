import { test, expect } from "@playwright/test";

test("real models: sample text, compare both, responsive results", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "分析", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("文章", { exact: true })
    .fill("今日はとても楽しかった！");
  await page.getByRole("button", { name: "分析", exact: true }).click();
  for (const name of ["LoRAの結果", "Full FTの結果"]) {
    const card = page.getByRole("region", { name });
    await expect(card.locator(".prediction")).toBeVisible({ timeout: 90000 });
    await expect(card.locator(".prob-row")).toHaveCount(5);
  }
  await page.screenshot({ path: "../.local/desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "../.local/mobile.png", fullPage: true });
  await page.getByLabel("文章", { exact: true }).fill("別の文章");
  await expect(page.getByRole("region", { name: "LoRAの結果" })).toHaveCount(0);
});

test("one API error keeps the other model result and allows retry", async ({
  page,
}) => {
  await page.route("**/predict/full", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "Model unavailable" }),
    }),
  );
  await page.goto("/");
  await page.getByLabel("文章", { exact: true }).fill("明日は月曜日です。");
  await page.getByRole("button", { name: "分析", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "LoRAの結果" }).locator(".prediction"),
  ).toBeVisible({ timeout: 90000 });
  await expect(page.getByRole("alert")).toContainText(
    "モデルを読み込めません。",
  );
  await expect(
    page.getByRole("button", { name: "分析", exact: true }),
  ).toBeEnabled();
});
