export interface ParsedSseEvent {
  event: string;
  data: unknown;
}

// Parser nhỏ cho SSE vì fetch stream trả chunk tùy ý, không đảm bảo trùng ranh giới event.
export class SseParser {
  private buffer = "";

  // Gom chunk stream rời rạc thành từng SSE block hoàn chỉnh trước khi parse JSON.
  feed(chunk: string): ParsedSseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: ParsedSseEvent[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      if (block.trim()) events.push(parseBlock(block));
      boundary = this.buffer.indexOf("\n\n");
    }
    return events;
  }

  // Dùng để phát hiện stream kết thúc giữa chừng khi buffer vẫn còn dữ liệu chưa đóng block.
  hasPendingData(): boolean {
    return this.buffer.trim().length > 0;
  }
}

// Parse một block SSE theo format event/data để frontend hiểu được delta và message cuối.
function parseBlock(block: string): ParsedSseEvent {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length) throw new Error("invalid_response");
  try {
    return { event, data: JSON.parse(data.join("\n")) as unknown };
  } catch {
    throw new Error("invalid_response");
  }
}
