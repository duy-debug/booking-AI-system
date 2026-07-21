"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/features/auth/AuthProvider";

const NAV = [
  { href: "/admin", label: "Tổng quan" },
  { href: "/admin/shops", label: "Shop" },
  { href: "/admin/courses", label: "Course" },
  { href: "/admin/therapists", label: "Therapist" },
  { href: "/admin/shifts", label: "Ca làm việc" },
  { href: "/admin/bookings", label: "Booking" },
  { href: "/admin/restrictions", label: "Cấm khách" },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const { user, isLoading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r border-zinc-200 bg-white p-4">
        {user && (
          <>
            <h1 className="mb-6 px-2 text-lg font-bold text-zinc-900">Booking Admin</h1>
            <nav className="flex flex-col gap-1">
              {NAV.map((item) => {
                const active =
                  item.href === "/admin"
                    ? pathname === "/admin"
                    : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-lg px-3 py-2 text-sm font-medium ${
                      active
                        ? "bg-blue-50 text-blue-700"
                        : "text-zinc-700 hover:bg-zinc-100"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <div className="mt-6 border-t border-zinc-200 pt-4">
              <p className="px-2 text-xs text-zinc-500">{user.email}</p>
              <button
                onClick={() => signOut().then(() => router.replace("/login"))}
                className="mt-2 w-full rounded-lg px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
              >
                Đăng xuất
              </button>
            </div>
          </>
        )}
      </aside>
      <main className="relative flex-1 overflow-auto bg-zinc-50 p-6">
        {children}
        {(isLoading || !user) && (
          <div className="absolute inset-0 flex items-center justify-center bg-white text-zinc-500">
            Đang tải...
          </div>
        )}
      </main>
    </div>
  );
}
