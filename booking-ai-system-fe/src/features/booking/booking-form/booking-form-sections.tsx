"use client";

import { useFormContext, useWatch } from "react-hook-form";
import { Input } from "@/shared/components/ui/input";
import { Select } from "@/shared/components/ui/select";
import { Card } from "@/shared/components/ui/card";
import type { BookingFormValues } from "./booking-form.schema";
import type { CourseUiModel } from "@/features/course/course.types";
import type { TherapistUiModel } from "@/features/therapist/therapist.types";
import type { EligibilityResult } from "./booking-form.queries";
import { GENDERS, THERAPIST_REQUEST_TYPES } from "@/shared/types/common";

// --- Helper hiển thị lỗi field ---
function FieldError({ name }: { name: keyof BookingFormValues }) {
  const {
    formState: { errors },
  } = useFormContext<BookingFormValues>();
  const err = errors[name];
  if (!err) return null;
  return <p className="mt-1 text-xs text-red-600">{err.message as string}</p>;
}

// Ghi chú field chưa có backend (xem docs/missing-booking-fields.md).
function UnsupportedNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-amber-300 bg-amber-50 p-3 text-xs text-amber-700">
      {children}
    </div>
  );
}

// 1. BookingTimeSection
export function BookingTimeSection({
  shops,
  timeOptions,
}: {
  shops: { value: string; label: string }[];
  timeOptions: { value: string; label: string }[];
}) {
  const { register } = useFormContext<BookingFormValues>();
  const shopId = useWatch({ name: "shopId" });
  return (
    <Card title="Thời gian booking">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Select
            label="Shop"
            options={shops}
            disabled={!!shopId}
            {...register("shopId")}
          />
          <FieldError name="shopId" />
        </div>
        <div>
          <Input label="Ngày" type="date" {...register("bookingDate")} />
          <FieldError name="bookingDate" />
        </div>
        <div>
          <Select
            label="Giờ bắt đầu"
            options={timeOptions}
            {...register("startTime")}
          />
          <FieldError name="startTime" />
        </div>
        <div>
          <Input
            label="Số người"
            type="number"
            min={1}
            max={3}
            {...register("numberOfPeople", { valueAsNumber: true })}
          />
          <FieldError name="numberOfPeople" />
        </div>
      </div>
    </Card>
  );
}

// 2. CustomerSection
export function CustomerSection({
  eligibility,
  eligibilityLoading,
  onCheck,
}: {
  eligibility?: EligibilityResult | null;
  eligibilityLoading?: boolean;
  onCheck: () => void;
}) {
  const { register } = useFormContext<BookingFormValues>();
  const phone = useWatch({ name: "customerPhone" });
  return (
    <Card
      title="Khách hàng"
      actions={
        <button
          type="button"
          onClick={onCheck}
          disabled={!phone || eligibilityLoading}
          className="text-xs text-blue-600 hover:underline disabled:opacity-40"
        >
          {eligibilityLoading ? "Đang kiểm tra..." : "Kiểm tra SĐT"}
        </button>
      }
    >
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Input label="Số điện thoại" {...register("customerPhone")} />
          <FieldError name="customerPhone" />
        </div>
        <div>
          <Input label="Tên khách" {...register("customerName")} />
          <FieldError name="customerName" />
        </div>
      </div>
      {eligibility && (
        <div className="mt-2 rounded-md bg-zinc-50 p-2 text-xs text-zinc-600">
          {eligibility.customer ? (
            <span>
              Khách hiện tại: <b>{eligibility.customer.name ?? "(chưa tên)"}</b>{" "}
              · {eligibility.customer.is_member ? "Thành viên" : "Guest"} · visit:{" "}
              {eligibility.customer.visit_count}
            </span>
          ) : (
            <span>Khách mới — sẽ được tạo khi lưu.</span>
          )}
          {!eligibility.eligible && (
            <p className="mt-1 font-medium text-red-600">
              SĐT bị cấm đặt lịch (NG list).
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

// 3. CourseSection
export function CourseSection({ courses }: { courses: CourseUiModel[] }) {
  const { register } = useFormContext<BookingFormValues>();
  const mainOptions = courses
    .filter((c) => c.courseType === "main")
    .map((c) => ({
      value: c.id,
      label: `${c.name} (${c.durationMinutes}p)`,
    }));
  const addonOptions = courses
    .filter((c) => c.courseType === "addon")
    .map((c) => ({ value: c.id, label: `${c.name} (${c.durationMinutes}p)` }));

  return (
    <Card title="Dịch vụ (Course)">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Select
            label="Course chính"
            options={mainOptions}
            {...register("mainCourseId")}
          />
          <FieldError name="mainCourseId" />
        </div>
        <div>
          <Select
            label="Course thêm (addon)"
            options={addonOptions}
            multiple
            {...register("addonCourseIds")}
          />
          <FieldError name="addonCourseIds" />
        </div>
      </div>
    </Card>
  );
}

// 4. OptionSection — backend chưa có "option" riêng -> hiển thị notice.
export function OptionSection() {
  return (
    <Card title="Option">
      <UnsupportedNote>
        Backend chưa hỗ trợ trường <b>option</b> (phân loại gói/addon chi tiết).
        Đang dùng course addon thay thế. Xem{" "}
        <code>docs/missing-booking-fields.md</code>.
      </UnsupportedNote>
    </Card>
  );
}

// 5. TherapistSection
export function TherapistSection({ therapists }: { therapists: TherapistUiModel[] }) {
  const { register, watch } = useFormContext<BookingFormValues>();
  const requestType = watch("therapistRequestType");
  const therapistOptions = therapists.map((t) => ({
    value: t.id,
    label: `${t.name} (${t.gender === "male" ? "Nam" : "Nữ"})`,
  }));
  const genderOptions = GENDERS.map((g) => ({
    value: g,
    label: g === "male" ? "Nam" : "Nữ",
  }));
  return (
    <Card title="Therapist">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Select
            label="Yêu cầu therapist"
            options={THERAPIST_REQUEST_TYPES.map((t) => ({
              value: t,
              label:
                t === "none"
                  ? "Không yêu cầu"
                  : t === "specific"
                    ? "Cụ thể"
                    : "Theo giới tính",
            }))}
            {...register("therapistRequestType")}
          />
          <FieldError name="therapistRequestType" />
        </div>
        {requestType === "specific" && (
          <div>
            <Select
              label="Therapist cụ thể"
              options={therapistOptions}
              {...register("requestedTherapistId")}
            />
            <FieldError name="requestedTherapistId" />
          </div>
        )}
        {requestType === "gender" && (
          <div>
            <Select
              label="Giới tính"
              options={genderOptions}
              {...register("requestedGender")}
            />
            <FieldError name="requestedGender" />
          </div>
        )}
      </div>
    </Card>
  );
}

// 6. BodyConditionSection — unsupported
export function BodyConditionSection() {
  return (
    <Card title="Tình trạng cơ thể">
      <UnsupportedNote>
        Các trường <b>vị trí mệt/đau</b> và <b>vị trí không được chạm</b> chưa có
        trong DB. Chưa thể lưu. Xem <code>docs/missing-booking-fields.md</code>.
      </UnsupportedNote>
    </Card>
  );
}

// 7. BookingSourceSection — unsupported
export function BookingSourceSection() {
  return (
    <Card title="Nguồn booking">
      <UnsupportedNote>
        Trường <b>nguồn booking</b> (POS / Web / Hotline / Walk-in) chưa có trong
        schema. Xem <code>docs/missing-booking-fields.md</code>.
      </UnsupportedNote>
    </Card>
  );
}

// 8. PreferenceSection — unsupported (interval, chat, pressure, clothes)
export function PreferenceSection() {
  return (
    <Card title="Tùy chọn cá nhân">
      <UnsupportedNote>
        Các trường <b>interval</b>, <b>mức độ trò chuyện</b>, <b>lực massage</b>,{" "}
        <b>thay quần áo</b> chưa có trong DB. Xem{" "}
        <code>docs/missing-booking-fields.md</code>.
      </UnsupportedNote>
    </Card>
  );
}

// 9. NotesSection — unsupported
export function NotesSection() {
  return (
    <Card title="Ghi chú">
      <UnsupportedNote>
        Trường <b>ghi chú</b> (note) chưa có cột trong bảng bookings/reservations.
        Xem <code>docs/missing-booking-fields.md</code>.
      </UnsupportedNote>
    </Card>
  );
}

// 10. BookingSummary
export function BookingSummary({
  courses,
  availability,
  availabilityLoading,
}: {
  courses: CourseUiModel[];
  availability?: { available: boolean; message?: string } | null;
  availabilityLoading?: boolean;
}) {
  const { watch } = useFormContext<BookingFormValues>();
  const values = watch();
  const selected = courses.filter(
    (c) =>
      c.id === values.mainCourseId || values.addonCourseIds.includes(c.id),
  );
  const totalMin = selected.reduce((s, c) => s + c.durationMinutes, 0);
  const totalPrice = selected.reduce((s, c) => s + c.price, 0);

  return (
    <Card title="Tóm tắt">
      <dl className="space-y-1 text-sm">
        <div className="flex justify-between">
          <dt className="text-zinc-500">Tổng thời lượng</dt>
          <dd className="font-medium">{totalMin} phút</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-zinc-500">Ước tính giá</dt>
          <dd className="font-medium">
            {new Intl.NumberFormat("vi-VN", {
              style: "currency",
              currency: "VND",
              maximumFractionDigits: 0,
            }).format(totalPrice)}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-zinc-500">Số người</dt>
          <dd className="font-medium">{values.numberOfPeople}</dd>
        </div>
      </dl>
      <div className="mt-3">
        {availabilityLoading ? (
          <p className="text-xs text-zinc-500">Đang kiểm tra lịch trống...</p>
        ) : availability ? (
          availability.available ? (
            <p className="text-xs font-medium text-green-600">
              ✔ Khung giờ khả dụng
            </p>
          ) : (
            <p className="text-xs font-medium text-red-600">
              ✖ Không khả dụng: {availability.message ?? "trùng lịch"}
            </p>
          )
        ) : null}
      </div>
    </Card>
  );
}
