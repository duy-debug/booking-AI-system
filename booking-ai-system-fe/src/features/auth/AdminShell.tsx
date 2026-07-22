"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/features/auth/AuthProvider";
import {
  LayoutDashboard,
  Store,
  BookOpen,
  UsersRound,
  CalendarRange,
  CalendarCheck2,
  UserRoundX,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  CalendarClock,
  type LucideIcon,
} from "lucide-react";

type SidebarItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

const sidebarItems: SidebarItem[] = [
  { label: "Tổng quan", href: "/admin", icon: LayoutDashboard },
  { label: "Shop", href: "/admin/shops", icon: Store },
  { label: "Course", href: "/admin/courses", icon: BookOpen },
  { label: "Therapist", href: "/admin/therapists", icon: UsersRound },
  { label: "Ca làm việc", href: "/admin/shifts", icon: CalendarRange },
  { label: "Booking", href: "/admin/bookings", icon: CalendarCheck2 },
  { label: "Cấm khách", href: "/admin/restrictions", icon: UserRoundX },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const { user, isLoading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  const isSchedulePage = pathname === "/admin/bookings";

  return (
    <div className="flex h-dvh w-full min-w-0 overflow-hidden bg-zinc-50">
      <aside
        className={`${
          collapsed ? "md:w-14" : "md:w-56"
        } flex h-full w-14 shrink-0 flex-col overflow-hidden border-r border-zinc-200 bg-white transition-[width] duration-150`}
      >
        {user && (
          <>
            <div className="flex h-14 shrink-0 items-center justify-center border-b border-zinc-100 px-2 md:justify-between md:px-3">
              <Link
                href="/admin"
                className="flex min-w-0 items-center gap-2 overflow-hidden"
                title={collapsed ? "Booking Admin" : undefined}
                aria-label="Booking Admin"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white">
                  <CalendarClock className="h-4 w-4" aria-hidden="true" />
                </div>
                {!collapsed && (
                  <span className="hidden truncate text-sm font-semibold text-zinc-900 md:block">
                    Booking Admin
                  </span>
                )}
              </Link>
              <button
                onClick={() => setCollapsed((c) => !c)}
                className="hidden shrink-0 rounded p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 md:block"
                aria-label={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
              >
                {collapsed ? (
                  <PanelLeftOpen className="h-[18px] w-[18px]" aria-hidden="true" strokeWidth={1.8} />
                ) : (
                  <PanelLeftClose className="h-[18px] w-[18px]" aria-hidden="true" strokeWidth={1.8} />
                )}
              </button>
            </div>
            <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden overscroll-contain px-2 py-3">
              {sidebarItems.map((item) => {
                const Icon = item.icon;
                const active =
                  item.href === "/admin"
                    ? pathname === "/admin"
                    : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex min-h-9 items-center justify-center gap-3 rounded-md px-2 py-1.5 text-sm font-medium transition-colors md:justify-start ${
                      active
                        ? "bg-blue-50 text-blue-700"
                        : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
                    }`}
                    title={collapsed ? item.label : undefined}
                    aria-label={item.label}
                    aria-current={active ? "page" : undefined}
                  >
                    <Icon
                      className="h-[18px] w-[18px] shrink-0"
                      aria-hidden="true"
                      strokeWidth={1.8}
                    />
                    {!collapsed && <span className="hidden truncate md:block">{item.label}</span>}
                  </Link>
                );
              })}
            </nav>
            <div className="shrink-0 border-t border-zinc-100 bg-white px-2 py-2">
              {!collapsed && (
                <p className="mb-1 hidden truncate px-1 text-xs text-zinc-400 md:block">{user.email}</p>
              )}
              <button
                onClick={() => signOut().then(() => router.replace("/login"))}
                className="flex min-h-9 w-full items-center justify-center gap-3 rounded-md px-2 py-1.5 text-left text-xs text-red-500 hover:bg-red-50 md:justify-start"
                title={collapsed ? "Đăng xuất" : undefined}
                aria-label="Đăng xuất"
              >
                <LogOut
                  className="h-[18px] w-[18px] shrink-0"
                  aria-hidden="true"
                  strokeWidth={1.8}
                />
                {!collapsed && <span className="hidden md:inline">Đăng xuất</span>}
              </button>
            </div>
          </>
        )}
      </aside>
      <main className="relative h-full min-w-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain bg-zinc-50">
        <div
          className={
            isSchedulePage
              ? "h-full min-w-0"
              : "min-h-full min-w-0 p-4 sm:p-5 lg:p-6"
          }
        >
          {children}
        </div>
        {(isLoading || !user) && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white text-zinc-500">
            Đang tải...
          </div>
        )}
      </main>
    </div>
  );
}
