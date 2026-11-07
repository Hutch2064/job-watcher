import { chromium } from "playwright";
import assert from "node:assert/strict";

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:8765/browse.html");
  await page
    .getByText(/\d[\d,]* postings/)
    .first()
    .waitFor();
  await page.getByLabel("Search titles").fill("analyst portfolio");
  await page
    .getByText(/\d[\d,]* postings/)
    .first()
    .waitFor();
  assert.ok(
    await page.locator(".job").count(),
    "word-order-independent search should find roles",
  );
  await page.locator(".star").first().click();
  assert.equal(
    await page.locator(".star").first().getAttribute("aria-pressed"),
    "true",
  );
  await page.getByRole("button", { name: /Shortlist/ }).click();
  assert.ok(await page.getByText("Application status").count());
  await page.getByLabel("Application status").first().selectOption("Applied");
  await page.reload();
  assert.equal(
    await page.getByLabel("Application status").first().inputValue(),
    "Applied",
  );
  await page.goto("http://127.0.0.1:8765/market.html");
  await page.getByText("Market overview.").waitFor();
  await page.locator(".chart-card").first().waitFor();
  await page.goto("http://127.0.0.1:8765/index.html");
  await page.getByText("Source health").waitFor();
  const firstVisitContext = await browser.newContext();
  const firstVisit = await firstVisitContext.newPage();
  await firstVisit.goto("http://127.0.0.1:8765/index.html");
  await firstVisit.getByText("Source health").waitFor();
  await firstVisit.waitForFunction(
    () => navigator.serviceWorker.controller !== null,
  );
  await firstVisitContext.setOffline(true);
  await firstVisit.reload();
  await firstVisit.getByText(/Offline or unavailable/).waitFor();
  await firstVisit.getByText("Source health").waitFor();
  await firstVisitContext.close();
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}
