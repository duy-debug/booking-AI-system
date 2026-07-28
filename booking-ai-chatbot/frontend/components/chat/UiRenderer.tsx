"use client";

import { FormEvent, useState } from "react";
import { CalendarIcon, CheckIcon, ChevronIcon, ClockIcon, StoreIcon, UserIcon } from "@/components/common/Icons";
import type { ChatSelection, UiBlock } from "@/types/chat";

interface Props {
  ui: UiBlock;
  disabled: boolean;
  onSelect: (label: string, selection: ChatSelection) => void;
}

const entityByType: Partial<Record<UiBlock["type"], string>> = {
  shop_options: "shop_id",
  course_options: "main_course_id",
  people_options: "number_of_people",
  slot_options: "start_time",
  therapist_request_options: "therapist_request_type",
  therapist_options: "therapist_id",
  gender_options: "therapist_gender",
};

function OptionList({ ui, disabled, onSelect }: Props) {
  const entity = entityByType[ui.type];
  if (!entity) return null;
  return (
    <div className={`option-list ${ui.type}`}>
      {ui.options.map((option) => (
        <button
          type="button"
          key={option.id}
          disabled={disabled}
          onClick={() => onSelect(option.label, {
            entity,
            value: ui.type === "people_options" ? Number(option.id) : option.id,
            label: option.label,
            metadata: option.metadata,
          })}
        >
          <span className="option-icon">
            {ui.type === "shop_options" ? <StoreIcon /> : ui.type === "slot_options" ? <ClockIcon /> : <CheckIcon />}
          </span>
          <span><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</span>
          <ChevronIcon className="chevron" />
        </button>
      ))}
    </div>
  );
}

function AddonPicker({ ui, disabled, onSelect }: Props) {
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (id: string) => setSelected((current) =>
    current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  return (
    <div className="selection-card">
      <div className="check-grid">
        {ui.options.map((option) => (
          <button
            type="button"
            key={option.id}
            className={selected.includes(option.id) ? "checked" : ""}
            aria-pressed={selected.includes(option.id)}
            onClick={() => toggle(option.id)}
            disabled={disabled}
          >
            <span className="fake-check"><CheckIcon /></span>
            <span><strong>{option.label}</strong><small>{option.description}</small></span>
          </button>
        ))}
      </div>
      <button type="button" className="primary-action" disabled={disabled} onClick={() => onSelect(
        selected.length ? `Đã chọn ${selected.length} dịch vụ thêm` : "Không chọn dịch vụ thêm",
        { entity: "addon_course_ids", value: selected },
      )}>{selected.length ? "Tiếp tục" : "Bỏ qua"}</button>
    </div>
  );
}

function DatePicker({ ui, disabled, onSelect }: Props) {
  const minDate = String(ui.data.min_date || new Date().toISOString().slice(0, 10));
  const [date, setDate] = useState(minDate);
  return (
    <div className="inline-form">
      <label><span><CalendarIcon /> Ngày hẹn</span><input type="date" min={minDate} value={date} onChange={(e) => setDate(e.target.value)} disabled={disabled}/></label>
      <button type="button" className="primary-action" disabled={disabled || !date} onClick={() => onSelect(
        new Intl.DateTimeFormat("vi-VN", { dateStyle: "long" }).format(new Date(`${date}T00:00:00`)),
        { entity: "booking_date", value: date },
      )}>Chọn ngày này</button>
    </div>
  );
}

function CustomerForm({ disabled, onSelect }: Omit<Props, "ui">) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    onSelect(`${name || "Khách hàng"} · ${phone}`, { entity: "customer", value: { name, phone } });
  }
  return (
    <form className="structured-form" onSubmit={submit}>
      <label><span><UserIcon /> Họ và tên</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nguyễn An" maxLength={100} disabled={disabled}/></label>
      <label><span>Điện thoại</span><input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} placeholder="090 123 4567" inputMode="tel" pattern="0[0-9]{9,10}" required disabled={disabled}/></label>
      <button className="primary-action" disabled={disabled}>Tiếp tục</button>
    </form>
  );
}

function ManageForm({ ui, disabled, onSelect }: Props) {
  const existing = (ui.data.booking || {}) as Record<string, unknown>;
  const isUpdate = ui.type === "booking_update_form";
  const [bookingId, setBookingId] = useState(String(ui.data.booking_id || ""));
  const [phone, setPhone] = useState(String(ui.data.phone || ""));
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  function submit(event: FormEvent) {
    event.preventDefault();
    const value = {
      booking_id: bookingId || undefined,
      phone: phone || undefined,
      booking_date: date || undefined,
      start_time: time || undefined,
      cancel_reason: !isUpdate ? reason : undefined,
    };
    onSelect(isUpdate ? "Đã nhập lịch hẹn mới" : "Yêu cầu hủy lịch", { entity: "booking_manage", value });
  }
  return (
    <div className="manage-booking-stack">
      {Boolean(existing.booking_id) && <BookingDetailCard booking={existing} title="Booking hiện tại" showCode={false} />}
      <form className="structured-form" onSubmit={submit}>
        {!existing.booking_id && <>
          <label><span>Mã booking</span><input value={bookingId} onChange={(e) => setBookingId(e.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" required disabled={disabled}/></label>
          <label><span>Điện thoại</span><input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} placeholder="0901234567" pattern="0[0-9]{9,10}" required disabled={disabled}/></label>
        </>}
        {isUpdate && <>
          <div className="form-note">Bạn có thể đổi ngày, giờ hoặc cả hai.</div>
          <div className="form-row">
            <label><span>Ngày mới</span><input type="date" value={date} min={new Date().toISOString().slice(0, 10)} onChange={(e) => setDate(e.target.value)} disabled={disabled}/></label>
            <label><span>Giờ mới</span><input type="time" value={time} onChange={(e) => setTime(e.target.value)} disabled={disabled}/></label>
          </div>
        </>}
        {!isUpdate && <label><span>Lý do hủy (không bắt buộc)</span><textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} disabled={disabled}/></label>}
        <button className={isUpdate ? "primary-action" : "danger-action"} disabled={disabled || (isUpdate && !!existing.booking_id && !date && !time)}>
          {isUpdate ? "Kiểm tra lịch mới" : "Tiếp tục hủy lịch"}
        </button>
      </form>
    </div>
  );
}

function LookupForm({ ui, disabled, onSelect }: Props) {
  const [bookingId, setBookingId] = useState(String(ui.data.booking_id || ""));
  const [phone, setPhone] = useState(String(ui.data.phone || ""));
  return (
    <form className="structured-form" onSubmit={(event) => {
      event.preventDefault();
      onSelect("Tra cứu booking", { entity: "booking_lookup", value: { booking_id: bookingId, phone } });
    }}>
      <label><span>Mã booking</span><input value={bookingId} onChange={(e) => setBookingId(e.target.value)} placeholder="Mã UUID trong xác nhận" required disabled={disabled}/></label>
      <label><span>Điện thoại đặt lịch</span><input value={phone} onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))} placeholder="0901234567" pattern="0[0-9]{9,10}" required disabled={disabled}/></label>
      <button className="primary-action" disabled={disabled}>Tra cứu</button>
    </form>
  );
}

function Summary({ ui, disabled, onSelect }: Props) {
  const data = ui.data;
  const booking = (data.booking || data) as Record<string, unknown>;
  const changes = (data.changes || {}) as Record<string, unknown>;
  const confirmation = ui.options[0];
  return (
    <div className="booking-confirmation">
      <BookingDetailCard
        booking={booking}
        changes={changes}
        title={ui.type === "booking_cancel_summary" ? "Booking sẽ hủy" : ui.type === "booking_update_summary" ? "Booking sau thay đổi" : "Chi tiết lịch hẹn"}
        showCode={ui.type !== "booking_cancel_summary" && ui.type !== "booking_update_summary"}
      />
      {confirmation && <div className="booking-confirm-action"><button type="button" className={ui.type === "booking_cancel_summary" ? "danger-action" : "primary-action"} disabled={disabled} onClick={() => onSelect(
          confirmation.label,
          { entity: "confirmation_token", value: confirmation.id, label: confirmation.label },
        )}><CheckIcon /> {ui.type === "booking_cancel_summary" ? "Xác nhận hủy booking" : "Xác nhận thay đổi"}</button></div>}
    </div>
  );
}

function BookingResult({ ui }: { ui: UiBlock }) {
  const booking = ui.data as Record<string, unknown>;
  return (
    <div className="result-card">
      <div className="result-check"><CheckIcon /></div>
      <div><strong>{booking.status === "cancelled" ? "Lịch hẹn đã được hủy" : "Yêu cầu đã hoàn tất"}</strong>
      {Boolean(booking.booking_id) && <small>Mã booking · {String(booking.booking_id)}</small>}</div>
    </div>
  );
}

const statusLabels: Record<string, string> = {
  confirmed: "Đã xác nhận",
  pending: "Chờ xác nhận",
  cancelled: "Đã hủy",
  completed: "Đã hoàn thành",
  assigned: "Đã phân công",
};

function formatTime(value: unknown) {
  return typeof value === "string" ? value.slice(0, 5) : String(value || "—");
}

function formatPrice(value: unknown) {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(amount)
    : String(value || "");
}

function BookingDetailCard({
  booking,
  changes = {},
  title = "Chi tiết lịch hẹn",
  showCode = true,
}: {
  booking: Record<string, unknown>;
  changes?: Record<string, unknown>;
  title?: string;
  showCode?: boolean;
}) {
  const reservations = Array.isArray(booking.reservations)
    ? booking.reservations as Array<Record<string, unknown>>
    : [];
  const status = String(booking.status || "");
  const effectiveTime = changes.start_time
    ? formatTime(changes.start_time)
    : `${formatTime(booking.start_time)} – ${formatTime(booking.end_time)}`;
  const rows = [
    ["Ngày hẹn", changes.booking_date || booking.booking_date],
    ["Thời gian", effectiveTime],
    ["Số khách", booking.number_of_people],
    ["Tổng thời lượng", booking.total_duration_minutes ? `${booking.total_duration_minutes} phút` : null],
    ["Cửa hàng", booking.shop_name || "Chưa cập nhật"],
    ["Yêu cầu kỹ thuật viên", booking.therapist_request_type],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");

  return (
    <section className="booking-detail-card">
      <div className="booking-detail-head">
        <span><CalendarIcon /></span>
        <div><small>THÔNG TIN BOOKING</small><strong>{title}</strong></div>
        <b className={`booking-status status-${status}`}>{statusLabels[status] || status || "Không xác định"}</b>
      </div>
      {showCode && <div className="booking-code">
        <span>Mã booking</span><code>{String(booking.booking_id || "—")}</code>
      </div>}
      <dl className="booking-detail-grid">
        {rows.map(([label, value]) => <div key={String(label)}><dt>{String(label)}</dt><dd>{String(value)}</dd></div>)}
      </dl>
      {reservations.length > 0 && (
        <div className="reservation-list">
          <h4>Dịch vụ đã đặt</h4>
          {reservations.map((reservation, index) => {
            const courses = Array.isArray(reservation.courses)
              ? reservation.courses as Array<Record<string, unknown>>
              : [];
            return (
              <div className="reservation-person" key={String(reservation.reservation_id || index)}>
                <div className="reservation-person-head">
                  <strong>Khách {String(reservation.person_index || index + 1)}</strong>
                  <span>{formatTime(reservation.start_time)} – {formatTime(reservation.end_time)}</span>
                </div>
                {courses.map((course, courseIndex) => (
                  <div className="reserved-course" key={String(course.course_id || courseIndex)}>
                    <span>
                      <strong>{String(course.course_name_snapshot || "Dịch vụ")}</strong>
                      <small>{String(course.duration_snapshot || "—")} phút · {course.course_role === "addon" ? "Dịch vụ thêm" : "Dịch vụ chính"}</small>
                    </span>
                    <b>{formatPrice(course.price_snapshot)}</b>
                  </div>
                ))}
                {Boolean(reservation.therapist_name) && (
                  <small className="therapist-reference">Kỹ thuật viên: {String(reservation.therapist_name)}</small>
                )}
              </div>
            );
          })}
        </div>
      )}
      {status === "cancelled" && Boolean(booking.cancel_reason) && (
        <div className="booking-cancel-note">Lý do hủy: {String(booking.cancel_reason)}</div>
      )}
    </section>
  );
}

function BookingDetail({ ui }: { ui: UiBlock }) {
  return <BookingDetailCard booking={ui.data as Record<string, unknown>} />;
}

export function UiRenderer(props: Props) {
  const { ui } = props;
  if (entityByType[ui.type]) return <OptionList {...props} />;
  if (ui.type === "addon_options") return <AddonPicker {...props} />;
  if (ui.type === "date_picker") return <DatePicker {...props} />;
  if (ui.type === "customer_form") return <CustomerForm disabled={props.disabled} onSelect={props.onSelect} />;
  if (ui.type === "booking_lookup_form") return <LookupForm {...props} />;
  if (ui.type === "booking_update_form" || ui.type === "booking_cancel_form") return <ManageForm {...props} />;
  if (ui.type === "booking_summary" || ui.type === "booking_update_summary" || ui.type === "booking_cancel_summary" || ui.type === "confirmation") return <Summary {...props} />;
  if (ui.type === "booking_result") {
    const operation = String(ui.data.operation || "");
    return ui.data.booking_date
      ? <BookingDetailCard
          booking={ui.data}
          title={operation === "cancel_booking" ? "Booking đã hủy" : operation === "update_booking" ? "Booking đã cập nhật" : "Chi tiết booking"}
          showCode={!operation}
        />
      : <BookingResult ui={ui} />;
  }
  if (ui.type === "booking_detail") return <BookingDetail ui={ui} />;
  return null;
}
