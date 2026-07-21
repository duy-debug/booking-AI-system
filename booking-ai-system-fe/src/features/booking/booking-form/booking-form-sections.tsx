"use client";

import { Search, UserCheck, UserPlus } from "lucide-react";
import { useFormContext, useWatch } from "react-hook-form";
import type { CourseUiModel } from "@/features/course/course.types";
import type { TherapistUiModel } from "@/features/therapist/therapist.types";
import { GENDERS, THERAPIST_REQUEST_TYPES } from "@/shared/types/common";
import type { BookingFormValues } from "./booking-form.schema";
import type { EligibilityResult } from "./booking-form.queries";
import {
  courseCategoryStyles,
  groupCourseVariants,
  type CourseVariantGroup,
} from "./course-matrix";

const inputClass =
  "h-8 rounded border border-zinc-300 bg-white px-2 text-xs text-zinc-900 outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500";
const fieldLabelClass = "mb-1 block text-[11px] font-medium text-zinc-600";
const chipClass =
  "h-7 rounded border px-2.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1";

function WorkspaceRow({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`grid grid-cols-1 border-x border-t border-zinc-200 md:grid-cols-[132px_minmax(0,1fr)] ${className}`}>
      <div className="flex min-h-11 items-center border-b border-zinc-200 bg-zinc-50 px-3 py-2 text-xs font-semibold text-zinc-700 md:border-b-0 md:border-r">
        {label}
      </div>
      <div className="min-w-0 px-3 py-2">{children}</div>
    </section>
  );
}

function FieldError({ name }: { name: keyof BookingFormValues }) {
  const {
    formState: { errors },
  } = useFormContext<BookingFormValues>();
  const error = errors[name];
  if (!error) return null;
  return <span className="mt-1 block text-[11px] text-red-600">{error.message as string}</span>;
}

export function BookingBasicInfoRow({
  timeOptions,
  bookingCode,
}: {
  timeOptions: { value: string; label: string }[];
  bookingCode?: string;
}) {
  const { register } = useFormContext<BookingFormValues>();

  return (
    <WorkspaceRow label="Thông tin booking">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div>
          <label className={fieldLabelClass}>Ngày</label>
          <input type="date" className={`${inputClass} w-[150px]`} {...register("bookingDate")} />
          <FieldError name="bookingDate" />
        </div>
        <div>
          <label className={fieldLabelClass}>Giờ bắt đầu</label>
          <select className={`${inputClass} w-[100px]`} {...register("startTime")}>
            {timeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <FieldError name="startTime" />
        </div>
        <div>
          <label className={fieldLabelClass}>Số người</label>
          <input
            type="number"
            min={1}
            max={3}
            className={`${inputClass} w-16`}
            {...register("numberOfPeople", { valueAsNumber: true })}
          />
          <FieldError name="numberOfPeople" />
        </div>
        <div className="min-w-[190px] flex-1 max-w-[320px]">
          <label className={fieldLabelClass}>Mã booking</label>
          <div className="flex h-8 items-center rounded border border-zinc-200 bg-zinc-50 px-2 text-xs text-zinc-600">
            {bookingCode ? `#${bookingCode}` : "Tự động sau khi tạo"}
          </div>
        </div>
      </div>
    </WorkspaceRow>
  );
}

export function BookingCustomerRow({
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
  const customer = eligibility?.customer;

  return (
    <WorkspaceRow label="Khách hàng">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <div>
          <label className={fieldLabelClass}>Số điện thoại</label>
          <div className="flex items-center gap-1.5">
            <input
              className={`${inputClass} w-[170px]`}
              inputMode="tel"
              placeholder="0912 345 678"
              {...register("customerPhone")}
            />
            <button
              type="button"
              onClick={onCheck}
              disabled={!phone || eligibilityLoading}
              className="inline-flex h-8 items-center gap-1.5 rounded bg-blue-600 px-3 text-xs font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Search className="h-3.5 w-3.5" aria-hidden="true" />
              {eligibilityLoading ? "Đang tra" : "Tra cứu"}
            </button>
          </div>
          <FieldError name="customerPhone" />
        </div>
        <div className="min-w-[220px] flex-1 max-w-[360px]">
          <label className={fieldLabelClass}>Tên khách</label>
          <input className={`${inputClass} w-full`} placeholder="Họ và tên" {...register("customerName")} />
        </div>
        <div className="min-w-[260px] flex-1">
          <label className={fieldLabelClass}>Kết quả tra cứu</label>
          <div className="flex min-h-8 flex-wrap items-center gap-2 rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-[11px] text-zinc-600">
            {!eligibility && <span className="text-zinc-400">Chưa tra cứu khách hàng</span>}
            {eligibility && customer && (
              <>
                <UserCheck className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
                <strong className="text-zinc-800">{customer.name ?? "Khách hiện có"}</strong>
                <span>{customer.is_member ? "Thành viên" : "Khách thường"}</span>
                {customer.member_rank && <span>Hạng {customer.member_rank}</span>}
                <span>{customer.visit_count} lần ghé</span>
              </>
            )}
            {eligibility && !customer && eligibility.eligible && (
              <>
                <UserPlus className="h-3.5 w-3.5 text-blue-600" aria-hidden="true" />
                <span>Khách mới, hồ sơ sẽ được tạo cùng booking</span>
              </>
            )}
            {eligibility && !eligibility.eligible && (
              <strong className="text-red-600">Số điện thoại không đủ điều kiện đặt lịch</strong>
            )}
          </div>
        </div>
      </div>
    </WorkspaceRow>
  );
}

function CourseGroupRows({
  groups,
  selectedIds,
  onToggle,
  emptyLabel,
}: {
  groups: CourseVariantGroup[];
  selectedIds: string[];
  onToggle: (course: CourseUiModel, selected: boolean) => void;
  emptyLabel: string;
}) {
  if (groups.length === 0) {
    return <div className="px-3 py-4 text-xs text-zinc-400">{emptyLabel}</div>;
  }

  return groups.map((group) => {
    const styles = courseCategoryStyles[group.category];
    return (
      <div
        key={group.key}
        className="grid min-h-11 grid-cols-[minmax(112px,160px)_minmax(0,1fr)] border-t border-zinc-200 first:border-t-0"
      >
        <div className="flex items-center border-r border-zinc-200 bg-zinc-50 p-2">
          <span className={`w-full rounded border px-2 py-1.5 text-center text-[11px] font-semibold ${styles.label}`}>
            {group.name}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 p-2">
          {group.variants.map((course) => {
            const selected = selectedIds.includes(course.id);
            return (
              <button
                key={course.id}
                type="button"
                aria-pressed={selected}
                title={`${course.name} · ${course.durationMinutes} phút · ${course.price.toLocaleString("vi-VN")}₫`}
                onClick={() => onToggle(course, selected)}
                className={`h-7 min-w-11 rounded border px-2 text-[11px] font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 ${
                  selected ? styles.selected : styles.idle
                }`}
              >
                {course.durationMinutes}
              </button>
            );
          })}
        </div>
      </div>
    );
  });
}

export function BookingCourseMatrix({ courses }: { courses: CourseUiModel[] }) {
  const { setValue, watch } = useFormContext<BookingFormValues>();
  const mainCourseId = watch("mainCourseId");
  const addonCourseIds = watch("addonCourseIds");
  const mainGroups = groupCourseVariants(courses.filter((course) => course.courseType === "main"));
  const addonGroups = groupCourseVariants(courses.filter((course) => course.courseType === "addon"));

  return (
    <WorkspaceRow label="Course" className="border-b">
      <div className="grid min-w-0 gap-2 xl:grid-cols-2">
        <div className="min-w-0 overflow-hidden rounded border border-zinc-200">
          <div className="flex h-8 items-center justify-between border-b border-zinc-200 bg-zinc-100 px-3 text-[11px] font-semibold text-zinc-700">
            <span>Course chính</span>
            <span className="font-normal text-zinc-500">Chọn một thời lượng</span>
          </div>
          <CourseGroupRows
            groups={mainGroups}
            selectedIds={mainCourseId ? [mainCourseId] : []}
            emptyLabel="Shop chưa có course chính đang hoạt động"
            onToggle={(course, selected) =>
              setValue("mainCourseId", selected ? "" : course.id, {
                shouldDirty: true,
                shouldValidate: true,
              })
            }
          />
        </div>
        <div className="min-w-0 overflow-hidden rounded border border-zinc-200">
          <div className="flex h-8 items-center justify-between border-b border-zinc-200 bg-zinc-100 px-3 text-[11px] font-semibold text-zinc-700">
            <span>Course thêm</span>
            <span className="font-normal text-zinc-500">Có thể chọn nhiều</span>
          </div>
          <CourseGroupRows
            groups={addonGroups}
            selectedIds={addonCourseIds}
            emptyLabel="Shop chưa có course thêm đang hoạt động"
            onToggle={(course, selected) => {
              const next = selected
                ? addonCourseIds.filter((id) => id !== course.id)
                : [...addonCourseIds, course.id];
              setValue("addonCourseIds", next, { shouldDirty: true });
            }}
          />
        </div>
      </div>
      <FieldError name="mainCourseId" />
    </WorkspaceRow>
  );
}

export function BookingTherapistRow({ therapists }: { therapists: TherapistUiModel[] }) {
  const { setValue } = useFormContext<BookingFormValues>();
  const requestType = useWatch({ name: "therapistRequestType" });
  const requestedTherapistId = useWatch({ name: "requestedTherapistId" });
  const requestedGender = useWatch({ name: "requestedGender" });

  const setRequestType = (type: BookingFormValues["therapistRequestType"]) => {
    setValue("therapistRequestType", type, { shouldDirty: true, shouldValidate: true });
    if (type !== "specific") setValue("requestedTherapistId", "", { shouldDirty: true });
    if (type !== "gender") setValue("requestedGender", undefined, { shouldDirty: true });
  };

  return (
    <WorkspaceRow label="Yêu cầu therapist" className="border-b">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div>
          <span className={fieldLabelClass}>Hình thức</span>
          <div className="flex flex-wrap gap-1.5">
            {THERAPIST_REQUEST_TYPES.map((type) => {
              const selected = requestType === type;
              const label = type === "none" ? "Không yêu cầu" : type === "gender" ? "Theo giới tính" : "Chỉ định cụ thể";
              return (
                <button
                  key={type}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setRequestType(type)}
                  className={`${chipClass} ${selected ? "border-blue-700 bg-blue-600 text-white" : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50"}`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <FieldError name="therapistRequestType" />
        </div>

        {requestType === "gender" && (
          <div>
            <span className={fieldLabelClass}>Giới tính therapist</span>
            <div className="flex gap-1.5">
              {GENDERS.map((gender) => {
                const selected = requestedGender === gender;
                return (
                  <button
                    key={gender}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setValue("requestedGender", gender, { shouldDirty: true, shouldValidate: true })}
                    className={`${chipClass} ${selected ? "border-blue-700 bg-blue-600 text-white" : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50"}`}
                  >
                    {gender === "male" ? "Nam" : "Nữ"}
                  </button>
                );
              })}
            </div>
            <FieldError name="requestedGender" />
          </div>
        )}

        {requestType === "specific" && (
          <div className="min-w-[280px] flex-1">
            <span className={fieldLabelClass}>Therapist cụ thể</span>
            <div className="flex max-h-20 flex-wrap gap-1.5 overflow-y-auto pr-1">
              {therapists.map((therapist) => {
                const selected = requestedTherapistId === therapist.id;
                return (
                  <button
                    key={therapist.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() =>
                      setValue("requestedTherapistId", therapist.id, {
                        shouldDirty: true,
                        shouldValidate: true,
                      })
                    }
                    className={`${chipClass} ${selected ? "border-blue-700 bg-blue-600 text-white" : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50"}`}
                  >
                    {therapist.name} · {therapist.gender === "male" ? "Nam" : "Nữ"}
                  </button>
                );
              })}
              {therapists.length === 0 && <span className="text-xs text-zinc-400">Không có therapist hoạt động</span>}
            </div>
            <FieldError name="requestedTherapistId" />
          </div>
        )}
      </div>
    </WorkspaceRow>
  );
}
