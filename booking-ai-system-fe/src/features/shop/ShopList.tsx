"use client";

import { ShopBreakSelector } from "@/features/shop/ShopBreakSelector";
import { useShops } from "@/features/shop/use-shop-queries";

// Chuyển trạng thái hoạt động của shop thành badge màu ngắn gọn, nhất quán ở table và mobile card.
function ShopStatus({ isActive }: { isActive: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        isActive
          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
          : "bg-zinc-100 text-zinc-600 ring-1 ring-zinc-200"
      }`}
    >
      {isActive ? "Hoạt động" : "Tạm tắt"}
    </span>
  );
}

// Tải danh sách shop và render bảng desktop hoặc card mobile cùng các trạng thái loading/error/empty.
export function ShopList() {
  const { data, isLoading, isError, error } = useShops();

  if (isLoading) {
    return (
      <div className="space-y-2" aria-label="Đang tải danh sách shop">
        {Array.from({ length: 5 }, (_, index) => (
          <div
            key={index}
            className="h-14 animate-pulse rounded-lg border border-zinc-200 bg-white"
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        Không thể tải danh sách shop: {error.message}
      </div>
    );
  }

  if (!data?.length) {
    return (
      <div className="rounded-lg border border-dashed border-zinc-300 bg-white px-4 py-10 text-center text-sm text-zinc-500">
        Chưa có shop nào.
      </div>
    );
  }

  return (
    <>
      <div className="hidden overflow-hidden rounded-lg border border-zinc-200 bg-white md:block">
        <table className="w-full table-fixed text-left text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="w-[24%] px-4 py-2.5">Shop</th>
              <th className="w-[18%] px-4 py-2.5">Mã hệ thống</th>
              <th className="w-[26%] px-4 py-2.5">Liên hệ</th>
              <th className="w-[16%] px-4 py-2.5">Nghỉ giữa booking</th>
              <th className="w-[16%] px-4 py-2.5">Trạng thái</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {data.map((shop) => (
              <tr key={shop.id} className="transition-colors hover:bg-zinc-50/80">
                <td className="px-4 py-3 align-top">
                  <p className="truncate font-medium text-zinc-900" title={shop.name}>
                    {shop.name}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-zinc-500" title={shop.address ?? undefined}>
                    {shop.address || "Chưa có địa chỉ"}
                  </p>
                </td>
                <td className="px-4 py-3 align-top text-xs text-zinc-600">
                  <p className="truncate" title={shop.code}>Code: {shop.code}</p>
                  <p className="mt-0.5 truncate" title={shop.posCode}>POS: {shop.posCode}</p>
                </td>
                <td className="px-4 py-3 align-top text-zinc-600">
                  <p className="truncate" title={shop.phone ?? undefined}>
                    {shop.phone || "Chưa có số điện thoại"}
                  </p>
                </td>
                <td className="px-4 py-3 align-top">
                  <ShopBreakSelector shop={shop} />
                </td>
                <td className="px-4 py-3 align-top">
                  <ShopStatus isActive={shop.isActive} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid min-w-0 gap-2 md:hidden">
        {data.map((shop) => (
          <article key={shop.id} className="min-w-0 rounded-lg border border-zinc-200 bg-white p-3 shadow-sm">
            <div className="flex min-w-0 items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="truncate text-sm font-semibold text-zinc-900">{shop.name}</h2>
                <p className="mt-0.5 truncate text-xs text-zinc-500">
                  {shop.code} · POS {shop.posCode}
                </p>
              </div>
              <div className="shrink-0">
                <ShopStatus isActive={shop.isActive} />
              </div>
            </div>
            <div className="mt-2 grid min-w-0 gap-1 border-t border-zinc-100 pt-2 text-xs text-zinc-600">
              <p className="truncate">{shop.address || "Chưa có địa chỉ"}</p>
              <p className="truncate">{shop.phone || "Chưa có số điện thoại"}</p>
              <div className="flex items-center justify-between gap-2 pt-1">
                <span>Nghỉ giữa booking</span>
                <ShopBreakSelector shop={shop} />
              </div>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
