import { z } from "zod";

const envSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().url("NEXT_PUBLIC_SUPABASE_URL phải là URL hợp lệ"),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1, "Thiếu NEXT_PUBLIC_SUPABASE_ANON_KEY"),
  NEXT_PUBLIC_API_URL: z.string().url("NEXT_PUBLIC_API_URL phải là URL hợp lệ"),
  NEXT_PUBLIC_SHOP_TIMEZONE: z.string().min(1).default("Asia/Ho_Chi_Minh"),
});

const envInput = {
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_SHOP_TIMEZONE: process.env.NEXT_PUBLIC_SHOP_TIMEZONE,
};

const parsed = envSchema.safeParse(envInput);

if (!parsed.success) {
  if (process.env.NODE_ENV !== "production") {
    console.warn(
      "[env] Thiếu hoặc sai biến môi trường:",
      parsed.error.flatten().fieldErrors,
    );
  }
}

export const env = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  shopTimezone: process.env.NEXT_PUBLIC_SHOP_TIMEZONE ?? "Asia/Ho_Chi_Minh",
} as const;

export type Env = typeof env;
