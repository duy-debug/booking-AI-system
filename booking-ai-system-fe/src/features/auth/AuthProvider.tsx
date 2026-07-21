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
import { supabase } from "@/shared/lib/supabase";

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

export function AuthProvider({ children }: { children: ReactNode }) {
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
    });

    return () => subscription.unsubscribe();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) return { error: error.message };
    return {};
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

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

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth phải được dùng trong <AuthProvider>");
  }
  return ctx;
}
