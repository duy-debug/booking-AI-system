import { type ReactNode } from "react";

// Bọc các Provider dùng chung: QueryClient + Auth (Supabase session).
// Không chứa layout trình bày. Đặt ở đây để app/ chỉ compose.
import { AppQueryClientProvider } from "@/shared/hooks/query-client-provider";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { AlertProvider } from "@/shared/components/AlertProvider";

// Ghép QueryClient, alert và authentication provider theo thứ tự dùng chung cho toàn ứng dụng.
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <AppQueryClientProvider>
      <AlertProvider>
        <AuthProvider>{children}</AuthProvider>
      </AlertProvider>
    </AppQueryClientProvider>
  );
}
