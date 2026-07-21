"use client";

import { createClient } from "@supabase/supabase-js";
import { env } from "@/shared/config/env";

// Supabase client chỉ dùng anon key (public). Session được quản lý tự động
// (refresh token qua cookie/httpOnly khi dùng SSR helpers). Không lưu JWT
// dài hạn thủ công vào localStorage — dùng getSession() của Supabase.
// Căn cứ: docs/frontend-analysis.md §6.1, §7.4.
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
