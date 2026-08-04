import { expect, test, type Page, type Route } from "@playwright/test";

interface CapturedRequest {
  conversation_id: string;
  message: string;
  idempotency_key: string;
}

function chatResponse(
  request: CapturedRequest,
  overrides: Partial<Record<string, unknown>> = {},
) {
  return {
    conversation_id: request.conversation_id,
    text: "Xin chào từ E2E",
    state: "selecting_shop",
    status: "success",
    instruction_template: null,
    quick_replies: ["Shibuya", "Shinjuku"],
    metadata: {},
    ...overrides,
  };
}

function sse(request: CapturedRequest, response = chatResponse(request)) {
  return [
    "event: started",
    `data: ${JSON.stringify({ conversation_id: request.conversation_id })}`,
    "",
    "event: message",
    `data: ${JSON.stringify(response)}`,
    "",
    "event: completed",
    `data: ${JSON.stringify({
      conversation_id: request.conversation_id,
      stream_status: "completed",
      dialog_status: response.status,
    })}`,
    "",
    "",
  ].join("\n");
}

async function mockChat(page: Page, requests: CapturedRequest[]) {
  await page.route("**/api/chat/stream", async (route) => {
    const request = route.request().postDataJSON() as CapturedRequest;
    requests.push(request);
    let response = chatResponse(request);
    if (request.message === "Xác nhận") {
      response = chatResponse(request, {
        text: "Đặt lịch đã hoàn tất.",
        state: "completed",
        status: "success",
        quick_replies: [],
        metadata: { booking_created: true },
      });
    } else if (request.message === "Không có slot") {
      response = chatResponse(request, {
        text: "Không còn khung giờ phù hợp, bạn hãy chọn ngày khác.",
        state: "selecting_date",
        status: "failure_handled",
        quick_replies: ["Ngày mai"],
      });
    } else if (request.message.startsWith("FAQ")) {
      response = chatResponse(request, {
        text: "Komorebi mở cửa từ 9 giờ.",
        state: "selecting_shop",
        quick_replies: [],
        metadata: { knowledge_answered: true },
      });
    }
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "Cache-Control": "no-cache" },
      body: sse(request, response),
    });
  });
}

async function send(page: Page, message: string) {
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.fill(message);
  await input.press("Enter");
}

test("sends the new body, renders text and quick replies without duplicate bubble", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  await send(page, "Xin chào");

  await expect(page.getByText("Xin chào từ E2E")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Shibuya" })).toBeVisible();
  expect(requests).toHaveLength(1);
  expect(requests[0]).toEqual({
    conversation_id: expect.any(String),
    message: "Xin chào",
    idempotency_key: expect.any(String),
  });
  expect(Object.keys(requests[0]).sort()).toEqual(["conversation_id", "idempotency_key", "message"]);
  await expect(page.getByRole("button", { name: "Ghi âm" })).toHaveCount(0);
});

test("quick reply creates a new turn and a new idempotency key", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  await send(page, "Bắt đầu");
  await page.getByRole("button", { name: "Shibuya" }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].message).toBe("Shibuya");
  expect(requests[1].conversation_id).toBe(requests[0].conversation_id);
  expect(requests[1].idempotency_key).not.toBe(requests[0].idempotency_key);
});

test("manual retry after an ambiguous truncation reuses the same idempotency key", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  let attempt = 0;
  await page.route("**/api/chat/stream", async (route: Route) => {
    const request = route.request().postDataJSON() as CapturedRequest;
    requests.push(request);
    attempt += 1;
    const response = chatResponse(request, { text: "Yêu cầu đang được xử lý" });
    const body = attempt === 1
      ? `event: message\ndata: ${JSON.stringify(response)}\n\n`
      : sse(request, response);
    await route.fulfill({ status: 200, contentType: "text/event-stream", body });
  });
  await page.goto("/");
  await send(page, "Xác nhận cuối");
  await expect(page.getByText(/yêu cầu có thể đã được xử lý/i)).toBeVisible();
  await page.getByRole("button", { name: "Thử lại" }).click();
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1]).toEqual(requests[0]);
  await expect(page.getByText("Yêu cầu đang được xử lý")).toHaveCount(1);
});

test("successful stateful turns cannot be replayed from the UI", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  await send(page, "Một turn stateful");
  await expect(page.getByText("Xin chào từ E2E")).toBeVisible();
  await expect(page.getByTitle("Tạo lại")).toHaveCount(0);
  expect(requests).toHaveLength(1);
  await expect(page.getByText("Xin chào từ E2E")).toHaveCount(1);
});

test("double submit sends one request", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.fill("Chỉ gửi một lần");
  await input.press("Enter");
  await input.press("Enter");
  await expect(page.getByText("Xin chào từ E2E")).toBeVisible();
  expect(requests).toHaveLength(1);
});

test("renders failure_handled as a normal assistant response", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  await send(page, "Không có slot");
  await expect(page.getByText("Không còn khung giờ phù hợp, bạn hãy chọn ngày khác.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Ngày mai" })).toBeVisible();
  await expect(page.getByText("Không gửi được tin nhắn")).toHaveCount(0);
});

test("renders generic no-code completion and hides terminal quick replies", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  await send(page, "Xác nhận");
  await expect(page.getByText("Đặt lịch đã hoàn tất.")).toBeVisible();
  await expect(page.getByText(/mã đặt lịch|booking code/i)).toHaveCount(0);
  await expect(page.locator(".quick-actions")).toHaveCount(0);
});

test("FAQ in a booking keeps the conversation id", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  await send(page, "Bắt đầu đặt lịch");
  await expect(page.getByText("Xin chào từ E2E")).toBeVisible();
  await send(page, "FAQ giờ mở cửa");
  await expect(page.getByText("Komorebi mở cửa từ 9 giờ.")).toBeVisible();
  expect(requests[1].conversation_id).toBe(requests[0].conversation_id);
});

test("SSE error displays its safe message", async ({ page }) => {
  await page.route("**/api/chat/stream", async (route) => {
    const request = route.request().postDataJSON() as CapturedRequest;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `event: error\ndata: ${JSON.stringify({
        conversation_id: request.conversation_id,
        code: "chat_processing_failed",
        message: "Không thể xử lý lúc này.",
      })}\n\n`,
    });
  });
  await page.goto("/");
  await send(page, "Test lỗi");
  await expect(page.getByText("Không thể xử lý lúc này.")).toBeVisible();
});

test("New Chat creates a new conversation and attempt key", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  await send(page, "Turn one");
  await expect(page.getByText("Xin chào từ E2E")).toBeVisible();
  await page.getByRole("button", { name: "Cuộc trò chuyện mới" }).click();
  await send(page, "Turn two");
  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1].conversation_id).not.toBe(requests[0].conversation_id);
  expect(requests[1].idempotency_key).not.toBe(requests[0].idempotency_key);
});

test("Shift+Enter creates a newline without sending", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
  await page.goto("/");
  const input = page.getByRole("textbox", { name: "Tin nhắn", exact: true });
  await input.fill("Dòng một");
  await input.press("Shift+Enter");
  await input.type("Dòng hai");
  await expect(input).toHaveValue("Dòng một\nDòng hai");
  expect(requests).toHaveLength(0);
});

test("chat fills the mobile viewport without horizontal overflow", async ({ page }) => {
  const requests: CapturedRequest[] = [];
  await mockChat(page, requests);
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
