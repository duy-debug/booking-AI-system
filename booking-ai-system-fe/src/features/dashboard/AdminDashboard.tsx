"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CalendarCheck2,
  CalendarRange,
  ShieldBan,
  Store,
  UsersRound,
} from "lucide-react";
import { useShops } from "@/features/shop/use-shop-queries";
import { AdminDataState } from "@/shared/components/admin/AdminUi";

const modules = [
  { href: "/admin/bookings", label: "Đặt lịch", description: "Theo dõi timeline và tạo lịch hẹn", icon: CalendarCheck2, tone: "bg-blue-50 text-blue-700" },
  { href: "/admin/shops", label: "Cửa hàng", description: "Quản lý chi nhánh và cấu hình nghỉ", icon: Store, tone: "bg-emerald-50 text-emerald-700" },
  { href: "/admin/courses", label: "Dịch vụ", description: "Quản lý dịch vụ chính và add-on", icon: BookOpen, tone: "bg-violet-50 text-violet-700" },
  { href: "/admin/therapists", label: "Kỹ thuật viên", description: "Quản lý nhân viên theo shop", icon: UsersRound, tone: "bg-cyan-50 text-cyan-700" },
  { href: "/admin/shifts", label: "Ca làm việc", description: "Xếp lịch làm việc theo ngày", icon: CalendarRange, tone: "bg-amber-50 text-amber-700" },
  { href: "/admin/restrictions", label: "Hạn chế khách", description: "Quản lý số điện thoại bị hạn chế", icon: ShieldBan, tone: "bg-red-50 text-red-700" },
] as const;

// Tải dữ liệu shop để tạo thống kê tổng quan và cung cấp lối tắt tới các phân hệ quản trị.
export function AdminDashboard() {
  const shopsQuery = useShops();
  const shops = shopsQuery.data ?? [];
  const activeCount = shops.filter((shop) => shop.isActive).length;
  const configuredBreakCount = shops.filter((shop) => shop.therapistBreakMinutes > 0).length;

  return (
    <AdminDataState loading={shopsQuery.isLoading} error={shopsQuery.error} empty={false} emptyMessage="">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-zinc-200 bg-white p-4"><p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Tổng shop</p><p className="mt-2 text-3xl font-semibold text-zinc-900">{shops.length}</p></div>
        <div className="rounded-xl border border-zinc-200 bg-white p-4"><p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Đang hoạt động</p><p className="mt-2 text-3xl font-semibold text-emerald-600">{activeCount}</p></div>
        <div className="rounded-xl border border-zinc-200 bg-white p-4"><p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Đã cấu hình nghỉ</p><p className="mt-2 text-3xl font-semibold text-blue-600">{configuredBreakCount}</p></div>
      </div>
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">Phân hệ quản trị</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {modules.map((module) => {
            const Icon = module.icon;
            return (
              <Link key={module.href} href={module.href} className="group flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-blue-200 hover:shadow-sm">
                <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${module.tone}`}><Icon className="h-5 w-5" aria-hidden="true" /></div>
                <div className="min-w-0 flex-1"><h3 className="font-medium text-zinc-900">{module.label}</h3><p className="truncate text-sm text-zinc-500">{module.description}</p></div>
                <ArrowRight className="h-4 w-4 shrink-0 text-zinc-300 transition group-hover:translate-x-0.5 group-hover:text-blue-500" aria-hidden="true" />
              </Link>
            );
          })}
        </div>
      </section>
    </AdminDataState>
  );
}
