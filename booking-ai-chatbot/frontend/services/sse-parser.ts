export interface ParsedSseEvent {
  event: string;
  data: unknown;
}

export class SseParser {
  private buffer = "";

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

  hasPendingData(): boolean {
    return this.buffer.trim().length > 0;
  }
}

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
