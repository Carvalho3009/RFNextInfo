import assert from "node:assert/strict";
import { createReadStream } from "node:fs";
import { createServer } from "node:http";
import { extname, join } from "node:path";
import { chromium } from "playwright";

const contentTypes = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css" };
const server = createServer((request, response) => {
  const pathname = new URL(request.url ?? "/", "http://localhost").pathname;
  const file = join("dist/dashboard", pathname === "/" ? "index.html" : pathname);
  response.setHeader("content-type", contentTypes[extname(file)] ?? "application/octet-stream");
  createReadStream(file).on("error", () => { response.statusCode = 404; response.end(); }).pipe(response);
});
await new Promise((resolve) => server.listen(5173, "127.0.0.1", resolve));
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1536, height: 1024 } });
  const errors = [];
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto("http://127.0.0.1:5173/?demo=1");
  assert.equal(await page.title(), "Poke Idle Supervisor");
  assert.equal(await page.getByRole("heading", { name: "principal" }).isVisible(), true);
  assert.equal(await page.getByText("MONITOR_COMBAT", { exact: true }).first().isVisible(), true);
  await page.getByRole("button", { name: /alt-lab/ }).click();
  await page.getByRole("button", { name: "Iniciar" }).click();
  assert.equal(await page.getByText("BOOT", { exact: true }).first().isVisible(), true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Abrir instâncias" }).click();
  assert.equal(await page.getByRole("complementary", { name: "Instâncias" }).isVisible(), true);
  assert.deepEqual(errors, []);
} catch (error) {
  const page = browser.contexts()[0]?.pages()[0];
  if (page) await page.screenshot({ path: "test-results/dashboard-error.png", fullPage: true }).catch(() => undefined);
  throw error;
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
