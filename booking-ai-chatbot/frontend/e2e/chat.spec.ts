import { expect, test } from "@playwright/test";

function sse(answer: string) {
  const done = {
    contract_version: "1.0",
    answer,
    intent: "general",
    conversation_id: "e2e-conversation",
    ui: null,
  };
  return [
    "event: start",
    'data: {"contract_version":"1.0","conversation_id":"e2e-conversation"}',
    "",
    "event: token",
    `data: ${JSON.stringify({ delta: answer })}`,
    "",
    "event: done",
    `data: ${JSON.stringify(done)}`,
    "",
    "",
  ].join("\n");
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/chat/stream", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "Cache-Control": "no-cache" },
      body: sse("Xin chào từ E2E"),
    });
  });
});

test("user sends a message and receives the SSE answer", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText(/Xin chào Nguyễn An/)).toBeVisible();
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.fill("Xin chào");
  await input.press("Enter");

  await expect(page.getByText("Xin chào", { exact: true })).toBeVisible();
  await expect(page.getByText("Xin chào từ E2E")).toBeVisible();
  await expect(input).toHaveValue("");
});

test("Shift+Enter creates a newline without sending", async ({ page }) => {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.fill("Dòng một");
  await input.press("Shift+Enter");
  await input.type("Dòng hai");

  await expect(input).toHaveValue("Dòng một\nDòng hai");
  await expect(page.getByText("Xin chào từ E2E")).not.toBeVisible();
});

test("stream failure shows a retry action", async ({ page }) => {
  await page.unroute("**/api/chat/stream");
  await page.route("**/api/chat/stream", (route) => route.abort("connectionrefused"));
  await page.goto("/");
  await expect(page.getByText(/Xin chào Nguyễn An/)).toBeVisible();
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.fill("Test lỗi");
  await input.press("Enter");

  await expect(page.getByText("Không gửi được tin nhắn")).toBeVisible();
  await expect(page.getByRole("button", { name: "Thử lại" })).toBeVisible();
});

test("message typed immediately after load is not lost", async ({ page }) => {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.fill("Tin nhắn tức thì");
  await input.press("Enter");

  await expect(page.getByText("Tin nhắn tức thì", { exact: true })).toBeVisible();
});

test("basic keyboard navigation reaches composer controls", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.focus();
  await input.fill("Nội dung");
  await expect(page.getByRole("button", { name: "Gửi tin nhắn" })).toBeVisible();
});

test("chat fills the mobile viewport without horizontal overflow", async ({ page }) => {
  await page.goto("/");
  const metrics = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    height: document.querySelector("main")?.getBoundingClientRect().height,
    viewportHeight: window.innerHeight,
  }));

  expect(metrics.scrollWidth).toBe(metrics.viewport);
  expect(Math.abs((metrics.height || 0) - metrics.viewportHeight)).toBeLessThanOrEqual(1);
});
