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

export function useShops(isActive?: boolean) {
  return useApiListQuery<AdminShopResponse, ShopUiModel>(
    ["shops", isActive],
    shopApi.list,
    isActive === undefined ? undefined : { is_active: isActive },
    toShopUiModel,
  );
}

export function useShop(id: UUID) {
  return useApiQuery<AdminShopResponse, ShopUiModel>(["shop", id], shopApi.byId(id), {
    select: (d) => toShopUiModel(d),
  });
}

export function useCreateShop() {
  return useApiMutation<ShopCreateInput, AdminShopResponse>((input) =>
    apiClient.post<AdminShopResponse>(shopApi.create, input),
  );
}

export function useUpdateShop(id: UUID) {
  return useApiMutation<ShopUpdateInput, AdminShopResponse>((input) =>
    apiClient.patch<AdminShopResponse>(shopApi.update(id), input),
  );
}

export type { ShopUiModel };
