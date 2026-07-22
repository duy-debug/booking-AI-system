"use client";

import { Search, UserCheck, UserPlus } from "lucide-react";
import { useFormContext, useWatch } from "react-hook-form";
import type { CourseUiModel } from "@/features/course/course.types";
import type { TherapistUiModel } from "@/features/therapist/therapist.types";
import type { AdminBookingDetailRaw } from "@/features/booking/schedule.types";
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
  numberOfPeopleReadOnly = false,
}: {
  timeOptions: { value: string; label: string; disabled?: boolean }[];
  bookingCode?: string;
  numberOfPeopleReadOnly?: boolean;
}) {
  const { register, setValue } = useFormContext<BookingFormValues>();
  const numberOfPeopleField = register("numberOfPeople", { valueAsNumber: true });

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
              <option key={option.value} value={option.value} disabled={option.disabled}>
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
            readOnly={numberOfPeopleReadOnly}
            aria-readonly={numberOfPeopleReadOnly}
            className={`${inputClass} w-16 ${numberOfPeopleReadOnly ? "bg-zinc-50 text-zinc-500" : ""}`}
            {...numberOfPeopleField}
            onChange={(event) => {
              void numberOfPeopleField.onChange(event);
              if (Number(event.target.value) > 1) {
                setValue("therapistRequestType", "none", {
                  shouldDirty: true,
                  shouldValidate: true,
                });
                setValue("requestedTherapistId", "", {
                  shouldDirty: true,
                  shouldValidate: true,
                });
                setValue("requestedGender", undefined, {
                  shouldDirty: true,
                  shouldValidate: true,
                });
              }
            }}
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

export function BookingEditDetails({
  detail,
}: {
  detail: AdminBookingDetailRaw;
}) {
  const customer = detail.customer;

  return (
    <>
      <WorkspaceRow label="Khách hàng">
        <div className="grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <span className={fieldLabelClass}>Tên khách</span>
            <strong className="text-zinc-800">{customer?.name || "Khách chưa có tên"}</strong>
          </div>
          <div>
            <span className={fieldLabelClass}>Số điện thoại</span>
            <span className="text-zinc-700">{customer?.phone || "-"}</span>
          </div>
          <div>
            <span className={fieldLabelClass}>Hạng thành viên</span>
            <span className="text-zinc-700">
              {customer?.is_member ? customer.member_rank || "Thành viên" : "Khách thường"}
            </span>
          </div>
          <div>
            <span className={fieldLabelClass}>Số lần ghé</span>
            <span className="text-zinc-700">{customer?.visit_count ?? 0}</span>
          </div>
        </div>
      </WorkspaceRow>

      <WorkspaceRow label="Phân công" className="border-b">
        {detail.reservations.length === 0 ? (
          <p className="py-2 text-xs text-zinc-500">Booking chưa có reservation.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-zinc-200 text-[11px] font-medium text-zinc-500">
                  <th className="px-2 py-2">Người</th>
                  <th className="px-2 py-2">Therapist</th>
                  <th className="px-2 py-2">Course</th>
                  <th className="px-2 py-2 text-right">Thời lượng</th>
                  <th className="px-2 py-2 text-right">Giá</th>
                </tr>
              </thead>
              <tbody>
                {detail.reservations.map((reservation) => {
                  const duration = reservation.courses.reduce(
                    (total, course) => total + course.duration_snapshot,
                    0,
                  );
                  const price = reservation.courses.reduce(
                    (total, course) => total + Number(course.price_snapshot),
                    0,
                  );
                  return (
                    <tr key={reservation.reservation_id} className="border-b border-zinc-100 last:border-b-0">
                      <td className="px-2 py-2 font-semibold text-zinc-800">
                        {reservation.person_index}
                      </td>
                      <td className="px-2 py-2 text-zinc-700">
                        {reservation.therapist.name || reservation.therapist.therapist_id}
                      </td>
                      <td className="px-2 py-2 text-zinc-700">
                        {reservation.courses.map((course) => course.course_name_snapshot).join(", ") || "-"}
                      </td>
                      <td className="px-2 py-2 text-right text-zinc-700">{duration} phút</td>
                      <td className="px-2 py-2 text-right font-medium text-zinc-800">
                        {price.toLocaleString("vi-VN")}₫
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </WorkspaceRow>
    </>
  );
}

export function BookingReservationEditor({
  courses,
  therapists,
}: {
  courses: CourseUiModel[];
  therapists: TherapistUiModel[];
}) {
  const { register, setValue, formState: { errors } } = useFormContext<BookingFormValues>();
  const reservations = (useWatch({ name: "reservations" }) ?? []) as BookingFormValues["reservations"];
  const autoAssignTherapists = useWatch({ name: "autoAssignTherapists" });
  const mainCourses = courses.filter((course) => course.courseType === "main");
  const addonCourses = courses.filter((course) => course.courseType === "addon");
  const rootError = errors.reservations?.message;
  const applyMainCourseToGroup = (courseId: string) => {
    reservations.forEach((_, index) => {
      setValue(`reservations.${index}.mainCourseId`, courseId, {
        shouldDirty: true,
        shouldValidate: true,
      });
    });
  };
  const applyAddonCoursesToGroup = (courseIds: string[]) => {
    reservations.forEach((_, index) => {
      setValue(`reservations.${index}.addonCourseIds`, [...courseIds], {
        shouldDirty: true,
        shouldValidate: true,
      });
    });
  };

  return (
    <WorkspaceRow label="Từng người" className="border-b">
      <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {reservations.map((reservation, index) => (
          <section key={reservation.reservationId ?? `new-${index}`} className="rounded border border-zinc-200 bg-zinc-50 p-3">
            <div className="mb-3 flex items-center justify-between">
              <strong className="text-xs text-zinc-800">Người {index + 1}</strong>
              <span className="text-[10px] text-zinc-400">
                {reservation.reservationId ? `#${reservation.reservationId.slice(0, 8)}` : "Mới"}
              </span>
            </div>
            <input type="hidden" {...register(`reservations.${index}.personIndex`, { valueAsNumber: true })} />

            <label className={fieldLabelClass}>Therapist</label>
            {autoAssignTherapists ? (
              <div className="mb-3 flex h-8 items-center rounded border border-blue-200 bg-blue-50 px-2 text-[11px] font-medium text-blue-700">
                Tự động phân công therapist khả dụng
              </div>
            ) : (
              <>
                <select className={`${inputClass} mb-3 w-full`} {...register(`reservations.${index}.therapistId`)}>
                  <option value="">Chọn therapist</option>
                  {therapists.map((therapist) => (
                    <option key={therapist.id} value={therapist.id}>
                      {therapist.name} · {therapist.gender === "male" ? "Nam" : "Nữ"}
                    </option>
                  ))}
                </select>
                {errors.reservations?.[index]?.therapistId?.message && (
                  <span className="mb-2 block text-[11px] text-red-600">{errors.reservations[index]?.therapistId?.message}</span>
                )}
              </>
            )}

            <label className={fieldLabelClass}>Course chính · áp dụng toàn nhóm</label>
            <select
              className={`${inputClass} mb-3 w-full`}
              value={reservation.mainCourseId}
              onChange={(event) => applyMainCourseToGroup(event.target.value)}
            >
              <option value="">Chọn course chính</option>
              {mainCourses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.name} · {course.durationMinutes} phút
                </option>
              ))}
            </select>
            {errors.reservations?.[index]?.mainCourseId?.message && (
              <span className="mb-2 block text-[11px] text-red-600">{errors.reservations[index]?.mainCourseId?.message}</span>
            )}

            <span className={fieldLabelClass}>Course thêm · áp dụng toàn nhóm</span>
            <div className="flex flex-wrap gap-1.5">
              {addonCourses.map((course) => {
                const selected = reservation.addonCourseIds.includes(course.id);
                return (
                  <button
                    key={course.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => {
                      const next = selected
                        ? reservation.addonCourseIds.filter((id) => id !== course.id)
                        : [...reservation.addonCourseIds, course.id];
                      applyAddonCoursesToGroup(next);
                    }}
                    className={`${chipClass} ${selected ? "border-blue-700 bg-blue-600 text-white" : "border-zinc-300 bg-white text-zinc-700"}`}
                  >
                    {course.name}
                  </button>
                );
              })}
              {addonCourses.length === 0 && <span className="text-[11px] text-zinc-400">Không có course thêm</span>}
            </div>
          </section>
        ))}
      </div>
      {rootError && <span className="mt-2 block text-[11px] text-red-600">{rootError}</span>}
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
  const numberOfPeople = useWatch({ name: "numberOfPeople" });

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
              const disabled = type === "specific" && numberOfPeople > 1;
              const label = type === "none" ? "Không yêu cầu" : type === "gender" ? "Theo giới tính" : "Chỉ định cụ thể";
              return (
                <button
                  key={type}
                  type="button"
                  aria-pressed={selected}
                  disabled={disabled}
                  title={disabled ? "Booking nhóm không thể chỉ định một therapist cụ thể" : undefined}
                  onClick={() => setRequestType(type)}
                  className={`${chipClass} disabled:cursor-not-allowed disabled:opacity-40 ${selected ? "border-blue-700 bg-blue-600 text-white" : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-50"}`}
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
