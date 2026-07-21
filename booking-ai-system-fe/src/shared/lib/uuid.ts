// Sinh UUID v4 (dùng cho Idempotency-Key khi tạo booking).
// Căn cứ: docs/frontend-analysis.md §6.5.
export function cryptoRandomUuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback (trường hợp môi trường cũ)
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
