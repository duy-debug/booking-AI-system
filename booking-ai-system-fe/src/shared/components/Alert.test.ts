import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Alert } from "./Alert";

describe("Alert", () => {
  it("renders errors as accessible alerts with a dismiss action", () => {
    const html = renderToStaticMarkup(createElement(Alert, {
      message: "Booking phải bắt đầu sau ít nhất 15 phút.",
      tone: "error",
      onDismiss: vi.fn(),
    }));

    expect(html).toContain('role="alert"');
    expect(html).toContain("Booking phải bắt đầu sau ít nhất 15 phút.");
    expect(html).toContain('aria-label="Đóng thông báo"');
  });

  it("uses the global three-second timeout", () => {
    const source = readFileSync(
      join(process.cwd(), "src/shared/components/AlertProvider.tsx"),
      "utf8",
    );
    expect(source).toContain("const ALERT_DURATION_MS = 3_000");
    expect(source).toContain("window.setTimeout(dismissItem, ALERT_DURATION_MS)");
  });
});
