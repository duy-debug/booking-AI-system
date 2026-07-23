"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useUpdateShop } from "@/features/shop/use-shop-queries";
import type { ShopUiModel } from "@/features/shop/shop.types";
import { useAlert } from "@/shared/components/AlertProvider";

const BREAK_OPTIONS = [0, 5, 10, 15] as const;

interface ShopBreakSelectorProps {
  shop: ShopUiModel;
  compact?: boolean;
}

// Cho phép admin cập nhật thời gian nghỉ của shop từ trang shop hoặc trực tiếp trên timeline.
export function ShopBreakSelector({
  shop,
  compact = false,
}: ShopBreakSelectorProps) {
  const updateShop = useUpdateShop(shop.id);
  const queryClient = useQueryClient();
  const { showError, showSuccess } = useAlert();

  const handleChange = async (value: string) => {
    try {
      await updateShop.mutateAsync({
        therapist_break_minutes: Number(value) as 0 | 5 | 10 | 15,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["shops"] }),
        queryClient.invalidateQueries({ queryKey: ["schedule"] }),
      ]);
      showSuccess("Đã cập nhật thời gian nghỉ giữa hai booking.");
    } catch {
      showError("Không thể cập nhật thời gian nghỉ giữa hai booking.");
    }
  };

  return (
    <select
      value={shop.therapistBreakMinutes}
      onChange={(event) => void handleChange(event.target.value)}
      disabled={updateShop.isPending}
      className={`rounded border border-zinc-300 bg-white px-2 text-xs text-zinc-700 disabled:opacity-50 ${
        compact ? "h-7" : "h-8"
      }`}
      aria-label={`Thời gian nghỉ giữa hai booking của ${shop.name}`}
    >
      {BREAK_OPTIONS.map((minutes) => (
        <option key={minutes} value={minutes}>
          {minutes} phút
        </option>
      ))}
    </select>
  );
}
