"use client";

import {
  QueryClient,
  QueryClientProvider,
  isServer,
} from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

// Tạo QueryClient với chính sách stale, retry và cache phù hợp cho dữ liệu quản trị.
function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Backend ít thay đổi thường xuyên; tránh refetch ngay khi remount.
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined;

// Dùng client riêng khi SSR và singleton trên trình duyệt để giữ cache qua các lần render.
function getQueryClient(): QueryClient {
  if (isServer) {
    return makeQueryClient();
  }
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}

// Cấp QueryClient ổn định cho toàn bộ query và mutation nằm dưới cây component.
export function AppQueryClientProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(getQueryClient);
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
