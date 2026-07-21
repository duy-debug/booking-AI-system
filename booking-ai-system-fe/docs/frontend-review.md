# Frontend Review — Schedule Feature & Booking Drawer/Form

**Người review:** Principal Frontend Engineer
**Phạm vi:** `booking-ai-system-fe` — schedule board + booking drawer/form (tạo/sửa)
**Stack:** Next.js 16 (App Router), TypeScript strict, Tailwind v4, TanStack Query, React Hook Form + Zod, vitest.
**Hợp đồng backend:** response bọc `{ data, meta? }`; lỗi RFC 9457 (`ApiError` có `code`); timezone naive (FE ép `SHOP_TIMEZONE`); booking qua nửa đêm mất ngày kết thúc.
**Trạng thái kiểm tra:** `lint` ✅ / `typecheck` ✅ / `test` 21 passed ✅ / `build` ✅ (sau khi sửa).

---

## Tổng quan đánh giá (checklist)

| Hạng mục | Kết luận |
|----------|----------|
| Kiến trúc thư mục | ✅ feature-based, tách rõ `booking-form/`, `schedule.*` |
| Component boundaries | ✅ presentational chỉ nhận props, không gọi API |
| Dependency direction | ✅ component → hooks → `apiClient` → mapper (1 chiều) |
| TypeScript strictness | ✅ strict, không `any` lộ liễu |
| Duplicate code | ⚠️ `buildTimelineRange` trùng (F11) — **đã sửa** |
| API error handling | ✅ `ApiError` ánh xạ field + global |
| Authentication | ✅ token từ Supabase session, không lưu localStorage |
| XSS | ✅ toàn bộ `{value}`, không `dangerouslySetInnerHTML` |
| JWT storage | ✅ chỉ qua Supabase (httpOnly/cache), không tự lưu |
| Timezone | ✅ `SHOP_TIMEZONE` nhất quán, không phụ thuộc tz trình duyệt |
| Booking conflict | ✅ 409 → availability + formError |
| Stale data | ✅ invalidate đúng keys sau save |
| Race condition | ⚠️ availability effect (F3) — **đã sửa** |
| Double submit | ⚠️ ref lock + state (F9/F21) — **đã sửa** |
| Query invalidation | ✅ `["schedule", shopId, date]` + `["admin-booking", id]` |
| Unnecessary re-render | ⚠️ `form.watch()` root (F13) — **đã sửa** |
| Accessibility | ⚠️ dialog/aria (F4) + block aria-label (F5) — **đã sửa** |
| Keyboard navigation | ⚠️ thiếu path tạo booking (F19) — chưa sửa |
| Responsive design | ✅ desktop panel / mobile fullscreen |
| Performance timeline | ⚠️ N+1 adapter (F1) — **đã sửa** |
| Test coverage | ⚠️ chỉ utils + mapper; thiếu test form/drawer |
| Loading/empty/error states | ✅ có đủ 3 trạng thái ở board |

### 10 câu hỏi đặc biệt

1. **Component quá lớn?** `BookingForm.tsx` ~220 dòng nhưng đã tách 10 section + effect ra `BookingLiveChecks`. Chấp nhận.
2. **API call trong presentational component?** ❌ Không. Mọi API qua `useApiQuery/useApiListQuery/useApiMutation`.
3. **Backend DTO dùng trực tiếp trong JSX?** ❌ Không. Raw DTO chỉ nằm trong `schedule.api.ts` / `booking.types.ts`, được map sang ViewModel trước khi render.
4. **State server copy vào Zustand/Context?** ❌ Không. Chỉ dùng TanStack Query cache.
5. **Mỗi ô thời gian là 1 component?** ✅ `BookingLayer` map từng booking thành `<button>`; `ScheduleHeader`/`TimeGrid` map tick.
6. **Dùng index làm React key?** ❌ Không. Dùng `therapistId`, `reservationId`, `shift_id`, `absoluteMinutes`.
7. **Date parsing phụ thuộc tz trình duyệt?** ❌ Không. Dùng `Intl.DateTimeFormat` với `timeZone: SHOP_TIMEZONE`.
8. **Double-submit được chặn?** ✅ `submitting` state + nút `disabled`.
9. **Optimistic update gây booking ảo?** ❌ Không dùng optimistic update.
10. **Query N+1 / request N+1?** ❌ Đã sửa (F1) — giờ 1 request `/api/admin/schedule`.

---

## Findings theo mức độ

### Critical
Không có.

### High

#### F1 — Schedule adapter N+1 (request cho mỗi booking)
- **File:** `src/features/schedule/schedule.queries.ts` (cũ), `schedule.mapper.ts` (cũ)
- **Code cũ:**
  ```ts
  await Promise.all(bookings.map(async (b) => {
    const detail = await apiClient.get(`/api/admin/bookings/${b.booking_id}`);
    // lấy reservation.therapist_id + courses
  }));
  ```
- **Tác động:** Ngày bận = N request (20–100+) mỗi lần load board, mỗi request mang Bearer token; render chậm/chập chờn; token gửi nhiều lần.
- **Cách sửa:** Chuyển sang `GET /api/admin/schedule` (backend đã có sẵn, trả về shifts + bookings + reservations + statuses trong 1 request). Thêm `schedule.api.ts` (raw DTO), refactor `schedule.mapper.ts` nhận `ScheduleResponseRaw`, `schedule.queries.ts` gọi endpoint mới. Key invalidate giữ nguyên `["schedule", shopId, date]` nên page không đổi.
- **Trạng thái:** ✅ Đã sửa.

### Medium

#### F2 — `useAdminBookingDetail` bắn request rỗng ở chế độ tạo
- **File:** `src/features/schedule/booking-form/BookingDrawer.tsx:46`
- **Code cũ:** `useAdminBookingDetail(bookingId ?? ("" as UUID))`
- **Tác động:** Ở create mode gọi `GET /api/admin/bookings/` (id rỗng) → 404/405 vô ích.
- **Cách sửa:** Thêm option `enabled` vào hook; chỉ enable khi `isEdit`.
- **Trạng thái:** ✅ Đã sửa.

#### F3 — Availability effect race / không abort / chạy khi invalid
- **File:** `src/features/schedule/booking-form/BookingForm.tsx` (effect cũ)
- **Code cũ:** `setTimeout` async, cleanup chỉ `clearTimeout`, không huỷ fetch; chạy khi `startTime` chưa hợp lệ.
- **Tác động:** Kết quả cũ ghi đè kết quả mới (hiển thị sai "khả dụng"/"trùng"); request vô ích khi field sai.
- **Cách sửa:** Dùng `reqId` ref để bỏ kết quả cũ; gate bằng regex `HH:MM` + `numberOfPeople` 1–3; skip khi `submitting`. (Sau này tách vào `BookingLiveChecks`.)
- **Trạng thái:** ✅ Đã sửa.

#### F4 — Drawer thiếu a11y (dialog / esc / focus)
- **File:** `src/features/schedule/booking-form/BookingDrawer.tsx`
- **Code cũ:** `<div className="fixed inset-0 ...">` không có role.
- **Tác động:** Screen reader không nhận diện modal; không đóng bằng Esc; focus không quản lý.
- **Cách sửa:** `<aside role="dialog" aria-modal aria-labelledby tabIndex=-1>`; autofocus khi mở; Esc → `handleClose`; trả focus về trigger khi đóng.
- **Trạng thái:** ✅ Đã sửa.

#### F5 — Booking block thiếu `aria-label`
- **File:** `src/features/schedule/BookingLayer.tsx`
- **Code cũ:** `<button title={title} ...>` (chỉ `title`).
- **Tác động:** SR chỉ đọc "button".
- **Cách sửa:** Thêm `aria-label="Đặt lịch {tên} — {dịch vụ} — {trạng thái}"`.
- **Trạng thái:** ✅ Đã sửa.

#### F9 — `useUpdateBooking` luôn tạo với id rỗng ở create mode
- **File:** `src/features/schedule/booking-form/BookingForm.tsx:95`
- **Code cũ:** `useUpdateBooking(initial.bookingId ?? ("" as UUID))`
- **Tác động:** Hook rule giữ nguyên (ok) nhưng mang id rỗng gây nhầm lẫn / lãng phí.
- **Cách sửa:** `useUpdateBooking(isEdit ? initial.bookingId : "")` (vẫn giữ thứ tự hook).
- **Trạng thái:** ✅ Đã sửa.

#### F13 — Re-render toàn form mỗi keystroke (`form.watch()` root)
- **File:** `src/features/schedule/booking-form/BookingForm.tsx` (cũ: `const values = form.watch()`)
- **Tác động:** Gõ 1 ký tự → re-render form gồm 10 section (dù section con có `useWatch` riêng).
- **Cách sửa:** Tách 2 effect live (eligibility + availability) vào component con `BookingLiveChecks` dùng `useWatch` riêng → chỉ component con re-render; xóa `form.watch()` ở root.
- **Trạng thái:** ✅ Đã sửa.

#### F19 — Thiếu đường bàn phím để tạo booking mới
- **File:** `src/features/schedule/ResourceRow.tsx` (chỉ `onClick`), `SelectionLayer.tsx`
- **Tác động:** User chỉ chuột mới tạo được booking; không thể thao tác bằng bàn phím.
- **Cách sửa (đề xuất):** Thêm nút "Tạo booking" focusable trên mỗi resource row, hoặc hỗ trợ phím tắt. Chưa sửa (cần design).
- **Trạng thái:** ⏳ Chưa sửa (đề xuất).

### Low

#### F6 — Hardcode `PX_PER_MINUTE` trong `ScheduleBoard`
- **File:** `ScheduleBoard.tsx:61`
- **Code cũ:** `const totalWidth = (range.end - range.start) * 4;`
- **Cách sửa:** Import `PX_PER_MINUTE` từ `schedule.theme`.
- **Trạng thái:** ✅ Đã sửa.

#### F7 — Admin-email mặc định "allow" khi thiếu env
- **File:** `src/features/auth/AuthProvider.tsx:32`
- **Tác động:** Khi `NEXT_PUBLIC_ADMIN_EMAILS` thiếu, client coi mọi user là admin (chờ backend 403). Đã document là intentional.
- **Cách sửa (đề xuất):** Log dev warning khi thiếu env. Chưa sửa.
- **Trạng thái:** ⏳ Chưa sửa (optional).

#### F8 — Dead code `therapistNames` trong adapter cũ
- **File:** `schedule.queries.ts` (cũ)
- **Tác động:** Code chết gây nhầm lẫn.
- **Cách sửa:** Xóa cùng với F1.
- **Trạng thái:** ✅ Đã sửa (với F1).

#### F11 — `buildTimelineRange` định nghĩa trùng
- **File:** `schedule.mapper.ts` (cũ) và `schedule.utils.ts:127`
- **Cách sửa:** Xóa bản trong mapper, dùng bản utils (có 2 tham số bắt buộc).
- **Trạng thái:** ✅ Đã sửa.

#### F20 — Nút "Đặt lại" không reset state eligibility/availability
- **File:** `BookingForm.tsx` (`onClick={() => form.reset()}`)
- **Tác động:** Sau reset form, badge "khả dụng/trùng" cũ vẫn hiển thị.
- **Cách sửa (đề xuất):** Trong handler reset, thêm `setEligibility(null); setAvailability(null);`.
- **Trạng thái:** ⏳ Chưa sửa (minor).

#### F21 — `submitLock` ref gây lint `react-hooks/refs`
- **File:** `BookingForm.tsx` (cũ)
- **Tác động:** Config lint mới bắt đọc ref trong callback submit.
- **Cách sửa:** Bỏ ref, chỉ dùng `submitting` state + nút `disabled` (đã đủ chặn double-submit).
- **Trạng thái:** ✅ Đã sửa.

---

## Điểm tích cực (giữ nguyên)
- Presentational components không gọi API trực tiếp. ✅
- Raw DTO không nằm trong JSX (chỉ ViewModel). ✅
- `useCreateBooking` gửi `Idempotency-Key`; `useUpdateBooking` PATCH chỉ field cho phép. ✅
- `handleSaved` invalidate đúng 2 keys. ✅
- Timezone xử lý nhất quán qua `SHOP_TIMEZONE`. ✅
- `BookingLayer` dùng `key={reservationId}` (không dùng index). ✅
- XSS: không dùng `dangerouslySetInnerHTML`. ✅

## Thứ tự làm việc đã thực hiện
1. F6, F2, F3, F4, F5, F9, F21, F13, F11, F1+F8 — sửa trực tiếp.
2. Viết lại test `schedule.mapper.test.ts` cho signature mới (21 tests xanh).
3. Chạy `lint` / `typecheck` / `test` / `build` → tất cả xanh.

## Còn lại (đề xuất, chưa sửa)
- **F19** keyboard path tạo booking.
- **F7** dev warning thiếu env admin.
- **F20** reset state khi "Đặt lại".
- **Test coverage:** thiếu test cho `BookingForm`, `BookingDrawer`, `BookingLiveChecks`, `schedule.queries` (mock `apiClient`).
- **Conflict mapping:** `SLOT_CONFLICT` có thể set lỗi vào trường `startTime` thay vì chỉ global message.
