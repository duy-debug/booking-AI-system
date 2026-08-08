import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MessageItem } from "./MessageItem";
import type { ChatMessage } from "../../types/chat";

function assistantMessage(
  overrides: Partial<ChatMessage> = {},
): ChatMessage {
  return {
    id: "assistant-1",
    role: "assistant",
    text: "Bạn muốn đặt lịch cho bao nhiêu người?",
    createdAt: 1,
    response: {
      conversation_id: "conversation-1",
      text: "Bạn muốn đặt lịch cho bao nhiêu người?",
      state: "selecting_people",
      status: "success",
      instruction_template: null,
      quick_replies: ["1 người", "2 người"],
      metadata: { source_count: 1 },
    },
    ...overrides,
  };
}

describe("MessageItem text-only rendering", () => {
  it("renders assistant text without quick replies or helper labels", () => {
    const html = renderToStaticMarkup(
      <MessageItem
        message={assistantMessage()}
        latest
        streaming={false}
      />,
    );

    expect(html).toContain("Bạn muốn đặt lịch cho bao nhiêu người?");
    expect(html).not.toContain("1 người</button>");
    expect(html).not.toContain("2 người</button>");
    expect(html).not.toContain("Gợi ý trả lời");
    expect(html).not.toContain("Chạm để chọn nhanh");
  });

  it("does not render state labels from metadata-only state", () => {
    const html = renderToStaticMarkup(
      <MessageItem
        message={assistantMessage({
          text: "Xin mời tiếp tục.",
          response: {
            conversation_id: "conversation-1",
            text: "Xin mời tiếp tục.",
            state: "selecting_service",
            status: "success",
            instruction_template: null,
            quick_replies: ["Massage đá nóng 60 phút"],
            metadata: {},
          },
        })}
        latest
        streaming={false}
      />,
    );

    expect(html).toContain("Xin mời tiếp tục.");
    expect(html).not.toContain("Liệu trình");
    expect(html).not.toContain("Massage đá nóng 60 phút</button>");
  });

  it("renders user messages as one text bubble", () => {
    const html = renderToStaticMarkup(
      <MessageItem
        message={{
          id: "user-1",
          role: "user",
          text: "Komorebi Tân Bình",
          createdAt: 1,
          status: "sent",
        }}
        latest
        streaming={false}
      />,
    );

    expect(html).toContain("Komorebi Tân Bình");
    expect(html).toContain("Đã gửi");
  });
});
