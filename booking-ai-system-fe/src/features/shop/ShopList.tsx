"use client";

import { useShops } from "@/features/shop/use-shop-queries";
import { Card } from "@/shared/components/ui/card";

export function ShopList() {
  const { data, isLoading, isError, error } = useShops();

  if (isLoading) return <p className="text-zinc-500">Đang tải...</p>;
  if (isError) return <p className="text-red-600">Lỗi: {error.message}</p>;

  return (
    <div className="grid gap-4">
      {data?.map((shop) => (
        <Card key={shop.id} title={shop.name}>
          <p className="text-sm text-zinc-600">Mã: {shop.code}</p>
          <p className="text-sm text-zinc-600">POS: {shop.posCode}</p>
          <p className="text-sm text-zinc-600">
            Trạng thái: {shop.isActive ? "Hoạt động" : "Tắt"}
          </p>
        </Card>
      ))}
      {data?.length === 0 && <p className="text-zinc-500">Chưa có shop nào.</p>}
    </div>
  );
}
