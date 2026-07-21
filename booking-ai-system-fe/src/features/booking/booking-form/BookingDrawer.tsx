"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/shared/components/ui/button";
import { ApiError } from "@/shared/types/api-error";
import type { UUID } from "@/shared/types/common";
import { useAdminBookingDetail, useCancelBooking } from "@/features/booking/use-booking-queries";
import { absoluteMinutesToHHMM } from "../schedule.utils";
import type { BookingViewModel } from "../schedule.types";
import type { Selection } from "../SelectionLayer";
import { BookingForm } from "./BookingForm";
import type { BookingFormInitial } from "./booking-form.schema";

export type BookingDrawerState =
  | { kind: "create"; selection: Selection; shopId: UUID; bookingDate: string }
  | { kind: "edit"; booking: BookingViewModel; shopId: UUID; bookingDate: string }
  | null;

interface BookingDrawerProps {
  state: BookingDrawerState;
  onClose: () => void;
  onSaved: (bookingId: UUID) => void;
}

// Drawer tạo/chỉnh sửa booking.
// Desktop: panel bên phải; Mobile: full-screen editor.
export function BookingDrawer({ state, onClose, onSaved }: BookingDrawerProps) {
  if (!state) return null;
  return (
    <BookingDrawerInner state={state} onClose={onClose} onSaved={onSaved} />
  );
}

function BookingDrawerInner({
  state,
  onClose,
  onSaved,
}: {
  state: NonNullable<BookingDrawerState>;
  onClose: () => void;
  onSaved: (bookingId: UUID) => void;
}) {
  const isEdit = state.kind === "edit";
  const bookingId = isEdit ? state.booking.bookingId : undefined;

  const detailQuery = useAdminBookingDetail(bookingId ?? ("" as UUID), {
    enabled: isEdit,
  });
  const cancelMut = useCancelBooking();
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<Element | null>(null);

  // Unsaved-change warning khi đóng drawer
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // Accessibility: focus vào panel khi mở, Escape để đóng, khôi phục focus trigger.
  const handleClose = () => {
    if (dirty) {
      if (!window.confirm("Bạn có thay đổi chưa lưu. Đóng mà không lưu?")) return;
    }
    onClose();
  };

  useEffect(() => {
    triggerRef.current = document.activeElement;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      (triggerRef.current as HTMLElement | null)?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const initial: BookingFormInitial = useMemo(() => {
    if (state.kind === "create") {
      return {
        mode: "create",
        shopId: state.shopId,
        bookingDate: state.bookingDate,
        startTime: absoluteMinutesToHHMM(state.selection.startMinutes),
        therapistId: state.selection.therapistId as UUID | undefined,
      };
    }
    // edit: lấy từ admin detail nếu có, nếu chưa load dùng view model
    const d = detailQuery.data;
    return {
      mode: "edit",
      bookingId: state.booking.bookingId,
      shopId: state.shopId,
      bookingDate: state.booking.bookingDate,
      startTime: absoluteMinutesToHHMM(state.booking.startMinutes),
      therapistId: state.booking.therapistId as UUID | undefined,
      customerPhone: d?.customerId
        ? undefined
        : state.booking.customerPhone,
      customerName: state.booking.customerName ?? undefined,
    };
  }, [state, detailQuery.data]);

  const handleCancelBooking = async () => {
    if (!bookingId) return;
    setCancelling(true);
    setCancelError(null);
    try {
      await cancelMut.mutateAsync({ id: bookingId, cancelReason: "Huỷ từ admin" });
      setShowCancelConfirm(false);
      onSaved(bookingId);
      onClose();
    } catch (err) {
      setCancelError(
        err instanceof ApiError
          ? err.detail || "Huỷ thất bại"
          : "Huỷ thất bại",
      );
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/30" onClick={handleClose} />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="booking-drawer-title"
        tabIndex={-1}
        className="relative flex h-full w-full max-w-md flex-col bg-white shadow-xl outline-none max-md:max-w-full max-md:w-full"
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
          <h2 id="booking-drawer-title" className="text-lg font-semibold">
            {isEdit ? "Chỉnh sửa booking" : "Tạo booking mới"}
          </h2>
          <Button variant="ghost" onClick={handleClose}>
            Đóng
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {isEdit && detailQuery.isLoading && (
            <p className="text-sm text-zinc-500">Đang tải chi tiết booking...</p>
          )}
          {isEdit && detailQuery.isError && (
            <p className="text-sm text-red-600">
              Không tải được chi tiết booking. Vẫn có thể sửa giờ.
            </p>
          )}
          <BookingForm
            initial={initial}
            onDirtyChange={setDirty}
            onSaved={(id) => {
              setDirty(false);
              onSaved(id);
            }}
            onCancelBooking={() => setShowCancelConfirm(true)}
          />
        </div>
      </aside>

      {showCancelConfirm && (
        <div className="absolute inset-0 z-[60] flex items-center justify-center bg-black/40">
          <div className="w-80 rounded-lg bg-white p-5 shadow-xl">
            <p className="mb-4 text-sm text-zinc-800">
              Xác nhận huỷ booking này? Thao tác không thể hoàn tác.
            </p>
            {cancelError && (
              <p className="mb-2 text-xs text-red-600">{cancelError}</p>
            )}
            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                onClick={() => setShowCancelConfirm(false)}
                disabled={cancelling}
              >
                Không
              </Button>
              <Button variant="danger" onClick={handleCancelBooking} disabled={cancelling}>
                Huỷ booking
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
