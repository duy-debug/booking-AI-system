// Múi giờ của shop — backend KHÔNG chuẩn hóa múi giờ, frontend phải tự xử lý.
// Căn cứ: app/db/models/booking.py (start_time/end_time là TIME naive),
//         docs/frontend-analysis.md §6.7, §9.
import { env } from "@/shared/config/env";

export const SHOP_TIMEZONE = env.shopTimezone;

// Danh sách khung giờ làm việc mặc định (dùng cho UI chọn ca)
export const BUSINESS_HOURS = {
  open: "09:00",
  close: "22:00",
} as const;
