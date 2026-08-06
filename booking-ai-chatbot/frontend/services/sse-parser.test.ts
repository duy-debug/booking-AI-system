import { describe, expect, it } from "vitest";
import { SseParser } from "./sse-parser";

describe("SseParser", () => {
  it("buffers partial chunks", () => {
    const parser = new SseParser();
    expect(parser.feed("event: mess")).toEqual([]);
    expect(parser.feed("age\ndata: {\"text\":\"xin chào\"}\n\n")).toEqual([
      { event: "message", data: { text: "xin chào" } },
    ]);
  });

  it("parses multiple events in one chunk", () => {
    const parser = new SseParser();
    expect(parser.feed("event: started\ndata: {}\n\nevent: completed\ndata: {}\n\n"))
      .toEqual([
        { event: "started", data: {} },
        { event: "completed", data: {} },
      ]);
  });
});
