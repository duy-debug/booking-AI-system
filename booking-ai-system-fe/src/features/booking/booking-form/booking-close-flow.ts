export type CloseIntent = "close-form" | "open-discard-dialog";

// Quyết định đóng form ngay hay mở xác nhận dựa trên việc người dùng có thay đổi chưa lưu.
export function resolveCloseIntent(isDirty: boolean): CloseIntent {
  return isDirty ? "open-discard-dialog" : "close-form";
}

export type EscapeIntent =
  | "close-discard-dialog"
  | "close-cancel-dialog"
  | CloseIntent;

// Xác định lớp UI cần đóng khi nhấn Escape theo thứ tự ưu tiên dialog rồi mới đến form booking.
export function resolveEscapeIntent(input: {
  confirmCloseOpen: boolean;
  cancelBookingOpen: boolean;
  isDirty: boolean;
}): EscapeIntent {
  if (input.confirmCloseOpen) return "close-discard-dialog";
  if (input.cancelBookingOpen) return "close-cancel-dialog";
  return resolveCloseIntent(input.isDirty);
}
