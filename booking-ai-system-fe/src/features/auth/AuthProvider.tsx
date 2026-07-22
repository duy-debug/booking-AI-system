"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { Session, User } from "@supabase/supabase-js";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "@/shared/lib/supabase";
import { setApiAccessToken } from "@/shared/api/client";

// Auth foundation: dùng Supabase session (refresh tự động, không lưu JWT
// dài hạn thủ công vào localStorage — nguyên tắc 11).
// Căn cứ: docs/frontend-analysis.md §6.1, §7.4.

interface AuthState {
  user: User | null;
  session: Session | null;
  accessToken: string | null;
  isLoading: boolean;
  isAdmin: boolean;
  signIn: (email: string, password: string) => Promise<{ error?: string }>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

// Danh sách email admin được backend chấp nhận (phải khớp ADMIN_EMAILS backend).
// Đọc từ env để dễ cấu hình; nếu không set, dựa vào backend trả 403.
function isAdminEmail(email: string | undefined): boolean {
  if (!email) return false;
  const list = process.env.NEXT_PUBLIC_ADMIN_EMAILS;
  if (!list) return true; // backend là nguồn chân lý
  return list
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .includes(email.toLowerCase());
}

// Theo dõi Supabase session, cung cấp trạng thái đăng nhập và các thao tác sign-in/sign-out cho ứng dụng.
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    supabase.auth
      .getSession()
      .then(({ data }) => {
        setSession(data.session);
        setUser(data.session?.user ?? null);
        setAccessToken(data.session?.access_token ?? null);
        setApiAccessToken(data.session?.access_token ?? null);
      })
      .catch(() => {
        /* cho phép render form login */
      })
      .finally(() => setIsLoading(false));

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, sess) => {
      setSession(sess);
      setUser(sess?.user ?? null);
      setAccessToken(sess?.access_token ?? null);
      setApiAccessToken(sess?.access_token ?? null);
    });

    return () => subscription.unsubscribe();
  }, []);

  // Đăng nhập và đồng bộ session ngay từ kết quả Supabase trước khi trang admin bắt đầu gọi API.
  const signIn = useCallback(async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) return { error: error.message };

    setSession(data.session);
    setUser(data.session?.user ?? null);
    setAccessToken(data.session?.access_token ?? null);
    setApiAccessToken(data.session?.access_token ?? null);
    return {};
  }, []);

  // Hủy request của phiên cũ và xóa cache API trước khi đăng xuất để lỗi hoặc dữ liệu cũ không lọt sang phiên kế tiếp.
  const signOut = useCallback(async () => {
    setApiAccessToken(null);
    await queryClient.cancelQueries();
    queryClient.clear();
    await supabase.auth.signOut();
    setSession(null);
    setUser(null);
    setAccessToken(null);
  }, [queryClient]);

  const value: AuthState = {
    user,
    session,
    accessToken,
    isLoading,
    isAdmin: isAdminEmail(user?.email),
    signIn,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// Trả auth context hiện tại và báo lỗi rõ ràng nếu hook được gọi ngoài AuthProvider.
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth phải được dùng trong <AuthProvider>");
  }
  return ctx;
}
