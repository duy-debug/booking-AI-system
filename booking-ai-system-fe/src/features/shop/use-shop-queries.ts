"use client";

import { useApiListQuery, useApiMutation, useApiQuery, apiClient } from "@/shared/hooks/api";
import type { UUID } from "@/shared/types/common";
import {
  shopApi,
  toShopUiModel,
  type AdminShopResponse,
  type ShopCreateInput,
  type ShopUiModel,
  type ShopUpdateInput,
} from "./shop.types";

// Tải danh sách shop, hỗ trợ lọc trạng thái active và tự chuyển DTO sang ShopUiModel.
export function useShops(isActive?: boolean) {
  return useApiListQuery<AdminShopResponse, ShopUiModel>(
    ["shops", isActive],
    shopApi.list,
    isActive === undefined ? undefined : { is_active: isActive },
    toShopUiModel,
  );
}

// Tải chi tiết một shop theo ID và chỉ bật query khi ID hợp lệ.
export function useShop(id: UUID) {
  return useApiQuery<AdminShopResponse, ShopUiModel>(["shop", id], shopApi.byId(id), {
    select: (d) => toShopUiModel(d),
  });
}

// Tạo mutation thêm shop mới qua admin API và trả DTO shop vừa được lưu.
export function useCreateShop() {
  return useApiMutation<ShopCreateInput, AdminShopResponse>((input) =>
    apiClient.post<AdminShopResponse>(shopApi.create, input),
  );
}

// Tạo mutation cập nhật một phần thông tin shop được xác định bởi ID.
export function useUpdateShop(id: UUID) {
  return useApiMutation<ShopUpdateInput, AdminShopResponse>((input) =>
    apiClient.patch<AdminShopResponse>(shopApi.update(id), input),
  );
}

export type { ShopUiModel };
