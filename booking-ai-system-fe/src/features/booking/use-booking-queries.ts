"use client";

import { useApiListQuery, useApiMutation, useApiQuery, apiClient } from "@/shared/hooks/api";
import type { BookingStatus, UUID } from "@/shared/types/common";
import {
  bookingApi,
  toBookingListUi,
  type AdminBookingListItemRaw,
  type BookingListUi,
} from "./booking.types";
import type { AdminBookingDetailRaw } from "./schedule.types";

export interface BookingListQuery {
  shopId?: UUID;
  bookingDate?: string;
  status?: string;
  phone?: string;
  posBookingCode?: string;
  limit?: number;
  cursor?: string | null;
}

// Tải danh sách booking admin theo bộ lọc và ánh xạ từng DTO sang model danh sách.
export function useAdminBookings(query: BookingListQuery) {
  return useApiListQuery<AdminBookingListItemRaw, BookingListUi>(
    ["admin-bookings", query],
    bookingApi.list,
    {
      shop_id: query.shopId,
      booking_date: query.bookingDate,
      status: query.status,
      phone: query.phone,
      pos_booking_code: query.posBookingCode,
      limit: query.limit ?? 20,
      cursor: query.cursor,
    },
    toBookingListUi,
  );
}

// Tải chi tiết booking cho modal chỉnh sửa và cho phép caller điều khiển trạng thái enabled.
export function useAdminBookingDetail(
  id: UUID,
  options?: { enabled?: boolean },
) {
  return useApiQuery<AdminBookingDetailRaw>(
    ["admin-booking", id],
    bookingApi.detail(id),
    {
      enabled: options?.enabled,
    },
  );
}

export interface CancelBookingVars {
  id: UUID;
  cancelReason?: string;
}

export interface CancelBookingResponse {
  booking_id: UUID;
  status: BookingStatus;
}

// Gửi PATCH chuyển booking sang cancelled cùng lý do hủy do admin cung cấp.
export function cancelBooking({ id, cancelReason }: CancelBookingVars) {
  return apiClient.patch<CancelBookingResponse>(bookingApi.cancel(id), {
    status: "cancelled",
    cancel_reason: cancelReason,
  });
}

// Bọc thao tác hủy booking trong mutation để UI theo dõi loading, error và kết quả.
export function useCancelBooking() {
  return useApiMutation<CancelBookingVars, CancelBookingResponse>(cancelBooking);
}
