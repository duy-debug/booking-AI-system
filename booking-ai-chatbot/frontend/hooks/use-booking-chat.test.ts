import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const source = readFileSync("hooks/use-booking-chat.ts", "utf8");

describe("useBookingChat architecture", () => {
  it("aborts the active request during effect cleanup", () => {
    expect(source).toContain("abortRef.current?.abort()");
    expect(source).toContain("window.cancelAnimationFrame(frame)");
  });

  it("guards duplicate submission without frontend booking logic", () => {
    expect(source).toContain("inFlightRef.current");
    expect(source).not.toContain("idempotency_key");
    expect(source).not.toContain("fetch(");
    expect(source).not.toMatch(/WebSocket|EventSource|MediaRecorder|localhost:8000/);
  });
});
