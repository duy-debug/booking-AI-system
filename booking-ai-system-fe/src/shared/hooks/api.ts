"use client";

import {
  useMutation,
  useQuery,
  type UseMutationOptions,
  type UseQueryOptions,
  type UseQueryResult,
} from "@tanstack/react-query";
import { apiClient } from "@/shared/api/client";

// Wrapper quanh TanStack Query để gọi apiClient. Component trình bày KHÔNG
// gọi API trực tiếp — chỉ dùng các hook này (nguyên tắc 4, 8).
// Căn cứ: docs/frontend-analysis.md §7.3.

export function useApiQuery<T, TOut = T>(
  key: readonly unknown[],
  path: string,
  options?: Omit<UseQueryOptions<T, Error, TOut>, "queryKey" | "queryFn">,
): UseQueryResult<TOut, Error> {
  return useQuery<T, Error, TOut>({
    queryKey: key as unknown[],
    queryFn: () => apiClient.get<T>(path),
    ...options,
  });
}

// Tải API dạng danh sách, lấy trường data và ánh xạ từng DTO sang model hiển thị khi có mapper.
export function useApiListQuery<TRaw, TOut = TRaw>(
  key: readonly unknown[],
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
  mapFn?: (raw: TRaw) => TOut,
  options?: Omit<UseQueryOptions<TOut[], Error>, "queryKey" | "queryFn">,
) {
  return useQuery<TOut[], Error>({
    queryKey: key as unknown[],
    queryFn: async () => {
      const data = await apiClient.get<TRaw[]>(path, { query });
      return mapFn ? data.map(mapFn) : (data as unknown as TOut[]);
    },
    ...options,
  });
}

// Bọc mutationFn bằng TanStack Query để các feature dùng chung trạng thái pending, error và result.
export function useApiMutation<TVariables, TData>(
  fn: (vars: TVariables) => Promise<TData>,
  options?: Omit<UseMutationOptions<TData, Error, TVariables>, "mutationFn">,
) {
  return useMutation<TData, Error, TVariables>({
    mutationFn: fn,
    ...options,
  });
}

export { apiClient };
