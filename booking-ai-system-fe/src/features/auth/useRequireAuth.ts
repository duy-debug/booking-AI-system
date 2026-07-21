"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/AuthProvider";

// Guard cho khu vực admin: nếu chưa đăng nhập -> về /login.
// (Kiểm tra isAdmin quyền hạn thực tế do backend trả 403 khi gọi API.)
// Căn cứ: docs/frontend-analysis.md §7.4.
export function useRequireAuth() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  return { user, isLoading };
}
