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
  const rows = [
    ["Cửa hàng", booking.shop_name || booking.shop_id],
    ["Dịch vụ", booking.main_course_name],
    ["Ngày", changes.booking_date || booking.booking_date],
    ["Thời gian", changes.start_time || booking.start_time],
    ["Số khách", booking.number_of_people],
    ["Khách hàng", booking.customer_name],
    ["Điện thoại", booking.customer_phone],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
  const confirmation = ui.options[0];
  return (
    <div className="summary-card">
      <div className="summary-head"><span><CalendarIcon /></span><div><small>XÁC NHẬN THÔNG TIN</small><strong>Chi tiết lịch hẹn</strong></div></div>
      <dl>{rows.map(([label, value]) => <div key={String(label)}><dt>{String(label)}</dt><dd>{String(value)}</dd></div>)}</dl>
      {confirmation && <button type="button" className={ui.type === "booking_cancel_summary" ? "danger-action" : "primary-action"} disabled={disabled} onClick={() => onSelect(
        confirmation.label,
        { entity: "confirmation_token", value: confirmation.id, label: confirmation.label },
      )}><CheckIcon /> {confirmation.label}</button>}
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

export function UiRenderer(props: Props) {
  const { ui } = props;
  if (entityByType[ui.type]) return <OptionList {...props} />;
  if (ui.type === "addon_options") return <AddonPicker {...props} />;
  if (ui.type === "date_picker") return <DatePicker {...props} />;
  if (ui.type === "customer_form") return <CustomerForm disabled={props.disabled} onSelect={props.onSelect} />;
  if (ui.type === "booking_lookup_form") return <LookupForm {...props} />;
  if (ui.type === "booking_update_form" || ui.type === "booking_cancel_form") return <ManageForm {...props} />;
  if (ui.type === "booking_summary" || ui.type === "booking_update_summary" || ui.type === "booking_cancel_summary" || ui.type === "confirmation") return <Summary {...props} />;
  if (ui.type === "booking_result" || ui.type === "booking_detail") return <BookingResult ui={ui} />;
  return null;
}
