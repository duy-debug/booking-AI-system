import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Bảo vệ đường thời gian hiện tại luôn kéo dài hết chiều cao danh sách therapist.
describe("CurrentTimeLine", () => {
  it("neo cả cạnh trên và dưới để đường đỏ có chiều cao", () => {
    const source = readFileSync(
      join(process.cwd(), "src/features/booking/CurrentTimeLine.tsx"),
      "utf8",
    );

    expect(source).toContain("absolute inset-y-0");
    expect(source).toContain("h-full w-px bg-red-500");
    expect(source).toContain("absoluteMinutesToHHMM(x)");
    expect(source).toContain("top: -HEADER_HEIGHT + 5");
  });
});
