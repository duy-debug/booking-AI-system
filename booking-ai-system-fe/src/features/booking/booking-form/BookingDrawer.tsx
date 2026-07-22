"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CalendarDays,
  CheckCircle2,
  Clock3,
  LoaderCircle,
  SearchCheck,
  UsersRound,
  X,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { useAlert } from "@/shared/components/AlertProvider";
import { ApiError } from "@/shared/types/api-error";
import type { UUID } from "@/shared/types/common";
import { useAdminBookingDetail, useCancelBooking } from "@/features/booking/use-booking-queries";
import { absoluteMinutesToHHMM } from "../schedule.utils";
import type { BookingViewModel } from "../schedule.types";
import type { Selection } from "../SelectionLayer";
import {
  BookingForm,
  type BookingFormHandle,
  type BookingFormSummary,
} from "./BookingForm";
import type { BookingFormInitial } from "./booking-form.schema";
import { resolveCloseIntent, resolveEscapeIntent } from "./booking-close-flow";

export type BookingDrawerState =
  | {
      kind: "create";
      selection: Selection;
      shopId: UUID;
      bookingDate: string;
      timezone: string;
      minimumBookingAdvanceMinutes: number;
    }
  | { kind: "edit"; booking: BookingViewModel; shopId: UUID; bookingDate: string }
  | null;

interface BookingDrawerProps {
  state: BookingDrawerState;
  onClose: () => void;
  onSaved: (bookingId: UUID) => void;
}

// Chỉ mount modal khi có state create/edit và chuyển xử lý chi tiết cho component nội bộ.
export function BookingDrawer({ state, onClose, onSaved }: BookingDrawerProps) {
  if (!state) return null;
  return <BookingModalInner state={state} onClose={onClose} onSaved={onSaved} />;
}

// ─── Modal inner ────────────────────────────────────────────────────────
// Điều phối detail query, dirty state, lưu/hủy booking và các dialog xác nhận trong modal.
function BookingModalInner({
  state,
  onClose,
  onSaved,
}: {
  state: NonNullable<BookingDrawerState>;
  onClose: () => void;
  onSaved: (bookingId: UUID) => void;
}) {
  const router = useRouter();
  const { showError, showSuccess } = useAlert();
  const isEdit = state.kind === "edit";
  const bookingId = isEdit ? state.booking.bookingId : undefined;

  const detailQuery = useAdminBookingDetail(bookingId ?? ("" as UUID), {
    enabled: isEdit,
  });
  const cancelMut = useCancelBooking();
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmCloseOpen, setConfirmCloseOpen] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);
  const [availability, setAvailability] = useState<{ available: boolean; message?: string } | null>(null);
  const [availabilityLoading, setAvailabilityLoading] = useState(false);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [summary, setSummary] = useState<BookingFormSummary>({
    bookingDate: state.bookingDate,
    startTime:
      state.kind === "create"
        ? absoluteMinutesToHHMM(state.selection.startMinutes)
        : absoluteMinutesToHHMM(state.booking.startMinutes),
    numberOfPeople: 1,
    durationMinutes: 0,
    totalPrice: 0,
  });
  const formRef = useRef<BookingFormHandle>(null);

  // Clear footer state when modal opens fresh
  useEffect(() => { setAvailability(null); setAvailabilityLoading(false); /* eslint-disable-line react-hooks/set-state-in-effect */ }, [state]);

  useEffect(() => {
    if (detailQuery.isError) {
      showError("Không tải được đầy đủ chi tiết booking.");
    }
  }, [detailQuery.isError, showError]);

  // Đóng modal qua callback của trang cha để trạng thái drawer được đặt lại tập trung.
  const closeBookingForm = useCallback(() => onClose(), [onClose]);

  // Đóng ngay khi form sạch hoặc mở xác nhận nếu còn thay đổi chưa lưu.
  const requestClose = useCallback(() => {
    if (resolveCloseIntent(dirty) === "close-form") {
      closeBookingForm();
      return;
    }
    setConfirmCloseOpen(true);
  }, [closeBookingForm, dirty]);

  // Hủy ý định rời form và xóa navigation target đang chờ.
  const cancelDiscardChanges = useCallback(() => {
    setConfirmCloseOpen(false);
    setPendingNavigation(null);
  }, []);

  // Reset form, đóng modal và tiếp tục điều hướng sau khi người dùng chấp nhận bỏ thay đổi.
  const confirmDiscardChanges = useCallback(() => {
    const navigationTarget = pendingNavigation;
    formRef.current?.reset();
    setDirty(false);
    setConfirmCloseOpen(false);
    setPendingNavigation(null);
    closeBookingForm();
    if (navigationTarget) router.push(navigationTarget);
  }, [closeBookingForm, pendingNavigation, router]);

  useEffect(() => {
    // Phân giải phím Escape theo dialog đang mở và dirty state của form.
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const intent = resolveEscapeIntent({
        confirmCloseOpen,
        cancelBookingOpen: showCancelConfirm,
        isDirty: dirty,
      });
      if (intent === "close-discard-dialog") {
        cancelDiscardChanges();
      } else if (intent === "close-cancel-dialog") {
        setShowCancelConfirm(false);
      } else if (intent === "close-form") {
        closeBookingForm();
      } else {
        setConfirmCloseOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cancelDiscardChanges, closeBookingForm, confirmCloseOpen, dirty, showCancelConfirm]);

  useEffect(() => {
    // Chặn link nội bộ khi form bẩn để yêu cầu xác nhận trước khi mất dữ liệu.
    const interceptNavigation = (event: MouseEvent) => {
      if (!dirty || confirmCloseOpen || showCancelConfirm || event.defaultPrevented) return;
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest<HTMLAnchorElement>("a[href]");
      if (!anchor || anchor.target || anchor.hasAttribute("download")) return;
      const url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin || url.href === window.location.href) return;

      event.preventDefault();
      event.stopPropagation();
      setPendingNavigation(`${url.pathname}${url.search}${url.hash}`);
      setConfirmCloseOpen(true);
    };

    document.addEventListener("click", interceptNavigation, true);
    return () => document.removeEventListener("click", interceptNavigation, true);
  }, [confirmCloseOpen, dirty, showCancelConfirm]);

  const initial: BookingFormInitial = useMemo(() => {
    if (state.kind === "create") {
      return {
        mode: "create",
        shopId: state.shopId,
        bookingDate: state.bookingDate,
        startTime: absoluteMinutesToHHMM(state.selection.startMinutes),
        therapistId: state.selection.therapistId as UUID | undefined,
        timezone: state.timezone,
        minimumBookingAdvanceMinutes: state.minimumBookingAdvanceMinutes,
      };
    }
    const d = detailQuery.data;
    const firstReservation = d?.reservations[0];
    return {
      mode: "edit",
      bookingId: state.booking.bookingId,
      shopId: state.shopId,
      bookingDate: d?.booking_date ?? state.booking.bookingDate,
      startTime: d?.start_time?.slice(0, 5) ?? absoluteMinutesToHHMM(state.booking.startMinutes),
      therapistId:
        firstReservation?.therapist.therapist_id ??
        (state.booking.therapistId as UUID | undefined),
      customerPhone: d?.customer?.phone ?? state.booking.customerPhone,
      customerName: d?.customer?.name ?? state.booking.customerName ?? undefined,
      numberOfPeople: d?.number_of_people ?? 1,
      durationMinutes: d?.total_duration_minutes ?? 0,
      totalPrice: firstReservation?.courses.reduce(
        (total, course) => total + Number(course.price_snapshot),
        0,
      ) ?? 0,
    };
  }, [state, detailQuery.data]);

  // Gửi yêu cầu hủy booking, phát alert kết quả và làm mới timeline khi thành công.
  const handleCancelBooking = async () => {
    if (!bookingId) return;
    setCancelling(true);
    try {
      await cancelMut.mutateAsync({ id: bookingId, cancelReason: "Huỷ từ admin" });
      setShowCancelConfirm(false);
      showSuccess("Hủy booking thành công.");
      onSaved(bookingId);
      onClose();
    } catch (err) {
      showError(err instanceof ApiError ? err.detail || "Hủy booking thất bại." : "Hủy booking thất bại.");
    } finally {
      setCancelling(false);
    }
  };

  // Đánh dấu form sạch trước khi báo booking vừa lưu cho trang cha.
  const handleSaved = (id: UUID) => {
    setDirty(false);
    onSaved(id);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-1 sm:p-2">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/40" onClick={requestClose} />

      {/* Modal */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="booking-modal-title"
        className="relative flex h-[94vh] w-[98vw] flex-col overflow-hidden rounded border border-zinc-300 bg-white shadow-lg outline-none max-sm:h-[100dvh] max-sm:w-screen max-sm:rounded-none"
      >
        {/* ═══ Header ═══ */}
        <div className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-zinc-300 bg-white px-3 py-2">
          <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1.5">
            <h2 id="booking-modal-title" className="text-sm font-bold text-zinc-900">
              {isEdit ? "Chỉnh sửa booking" : "Tạo booking mới"}
            </h2>
            <span className="inline-flex items-center gap-1.5 text-xs text-zinc-600">
              <CalendarDays className="h-3.5 w-3.5 text-zinc-400" aria-hidden="true" />
              {summary.bookingDate}
            </span>
            <span className="inline-flex items-center gap-1.5 text-xs text-zinc-600">
              <Clock3 className="h-3.5 w-3.5 text-zinc-400" aria-hidden="true" />
              {summary.startTime}
            </span>
            <span className="inline-flex items-center gap-1.5 text-xs text-zinc-600">
              <UsersRound className="h-3.5 w-3.5 text-zinc-400" aria-hidden="true" />
              {summary.numberOfPeople} người
            </span>
            {isEdit && (
              <span className="rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700">
                #{state.booking.bookingId.slice(0, 8)}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={requestClose}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800"
            aria-label="Đóng"
            title="Đóng"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* ═══ Scrollable body ═══ */}
        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-2 sm:p-3">
          {isEdit && detailQuery.isLoading && (
            <p className="text-xs text-zinc-400 mb-3">Đang tải chi tiết booking...</p>
          )}
          {(!isEdit || !detailQuery.isLoading) && (
            <BookingForm
              key={isEdit ? `${bookingId}:${detailQuery.data ? "detail" : "fallback"}` : "create"}
              ref={formRef}
              initial={initial}
              editDetail={isEdit ? detailQuery.data : undefined}
              onDirtyChange={setDirty}
              onSaved={handleSaved}
              onAvailability={setAvailability}
              onAvailabilityLoading={setAvailabilityLoading}
              onSubmittingChange={setFormSubmitting}
              onSummaryChange={setSummary}
            />
          )}
        </div>

        {/* ═══ Footer ═══ */}
        <div className="flex min-h-12 shrink-0 flex-wrap items-center justify-between gap-2 border-t border-zinc-300 bg-zinc-50 px-3 py-2">
          {/* Left: errors + summary + availability */}
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            {isEdit ? (
              <span className="text-zinc-500">Cập nhật toàn bộ nhóm booking</span>
            ) : availabilityLoading ? (
              <span className="inline-flex items-center gap-1.5 text-zinc-500">
                <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                Đang kiểm tra
              </span>
            ) : availability ? (
              availability.available ? (
                <span className="inline-flex items-center gap-1.5 font-medium text-emerald-700">
                  <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Khả dụng
                </span>
              ) : (
                <span className="font-medium text-red-600">Không khả dụng</span>
              )
            ) : (
              <span className="text-zinc-500">Chưa kiểm tra</span>
            )}
            <span className="text-zinc-300">|</span>
            <span className="font-medium text-zinc-700">
              {summary.durationMinutes > 0 ? `${summary.durationMinutes} phút` : "Chưa chọn course"}
            </span>
            {summary.durationMinutes > 0 && (
              <span className="font-semibold text-blue-700">{summary.totalPrice.toLocaleString("vi-VN")}₫</span>
            )}
            <span className="text-zinc-500">{summary.numberOfPeople} booking</span>
          </div>

          {/* Right: actions */}
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" onClick={requestClose} disabled={cancelling || formSubmitting} className="h-8 px-3 text-xs">
              Đóng
            </Button>
            {!isEdit && (
              <Button
                type="button"
                variant="secondary"
                onClick={() => formRef.current?.checkAvailability()}
                disabled={cancelling || formSubmitting}
                loading={availabilityLoading}
                className="h-8 gap-1.5 px-3 text-xs"
              >
                <SearchCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Kiểm tra
              </Button>
            )}
            {isEdit && (
              <Button type="button" variant="danger" disabled={cancelling || formSubmitting} onClick={() => setShowCancelConfirm(true)} className="h-8 px-3 text-xs">
                Huỷ
              </Button>
            )}
            <Button type="submit" form="booking-form" disabled={cancelling} loading={formSubmitting} className="h-8 px-4 text-xs">
              {isEdit ? "Cập nhật" : "Tạo booking"}
            </Button>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmCloseOpen}
        title="Có thay đổi chưa lưu"
        description="Bạn đã chỉnh sửa thông tin booking. Nếu đóng bây giờ, các thay đổi sẽ bị mất."
        cancelLabel="Tiếp tục chỉnh sửa"
        confirmLabel="Đóng không lưu"
        tone="danger"
        onCancel={cancelDiscardChanges}
        onConfirm={confirmDiscardChanges}
      />

      <ConfirmDialog
        open={showCancelConfirm}
        title="Hủy booking"
        description="Xác nhận hủy booking này? Thao tác không thể hoàn tác."
        cancelLabel="Không"
        confirmLabel="Hủy booking"
        tone="danger"
        isLoading={cancelling}
        onCancel={() => setShowCancelConfirm(false)}
        onConfirm={handleCancelBooking}
      />
    </div>
  );
}
