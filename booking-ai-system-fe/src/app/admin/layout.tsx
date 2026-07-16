"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Store, Scissors, Users, Calendar, ClipboardList, Ban,
} from "lucide-react";

const navItems = [
  { href: "/admin", label: "Tổng quan", icon: LayoutDashboard },
  { href: "/admin/shops", label: "Chi nhánh", icon: Store },
  { href: "/admin/courses", label: "Dịch vụ", icon: Scissors },
  { href: "/admin/therapists", label: "Therapist", icon: Users },
  { href: "/admin/shifts", label: "Ca làm", icon: Calendar },
  { href: "/admin/bookings", label: "Đặt lịch", icon: ClipboardList },
  { href: "/admin/restrictions", label: "NG list", icon: Ban },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push("/login");
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return <div className="flex min-h-screen items-center justify-center text-zinc-500">Đang tải...</div>;
  }

  if (!user) {
    return null;
  }

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-zinc-200 bg-white">
        <div className="border-b border-zinc-200 px-4 py-3 text-sm font-semibold text-zinc-900">
          Booking Admin
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${
                  isActive
                    ? "bg-blue-50 font-medium text-blue-700"
                    : "text-zinc-600 hover:bg-zinc-50"
                }`}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-zinc-200 px-4 py-3">
          <p className="text-xs text-zinc-500">{user?.email}</p>
          <button onClick={signOut} className="mt-1 text-xs text-red-600 hover:text-red-700">
            Đăng xuất
          </button>
        </div>
      </aside>

      <main className="flex-1 bg-zinc-50 p-6">{children}</main>
    </div>
  );
}
