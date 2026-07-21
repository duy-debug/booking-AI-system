"use client";

import { useApiListQuery, useApiMutation, useApiQuery, apiClient } from "@/shared/hooks/api";
import type { UUID } from "@/shared/types/common";
import {
  bookingApi,
  toBookingDetailUi,
  toBookingListUi,
  type AdminBookingListItemRaw,
  type BookingDetailRaw,
  type BookingDetailUi,
  type BookingListUi,
} from "./booking.types";

export interface BookingListQuery {
  shopId?: UUID;
  bookingDate?: string;
  status?: string;
  phone?: string;
  posBookingCode?: string;
  limit?: number;
  cursor?: string | null;
}

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

export function useAdminBookingDetail(
  id: UUID,
  options?: { enabled?: boolean },
) {
  return useApiQuery<BookingDetailRaw, BookingDetailUi>(
    ["admin-booking", id],
    bookingApi.detail(id),
    {
      enabled: options?.enabled,
      select: (d) => toBookingDetailUi(d),
    },
  );
}

export interface CancelBookingVars {
  id: UUID;
  cancelReason?: string;
}

export function useCancelBooking() {
  return useApiMutation<CancelBookingVars, BookingDetailUi>(({ id, cancelReason }) =>
    apiClient
      .patch<BookingDetailRaw>(bookingApi.cancel(id), {
        status: "cancelled",
        cancel_reason: cancelReason,
      })
      .then(toBookingDetailUi),
  );
}
