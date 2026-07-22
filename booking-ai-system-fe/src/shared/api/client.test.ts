import { beforeEach, describe, expect, it, vi } from "vitest";

const { getSession, refreshSession } = vi.hoisted(() => ({
  getSession: vi.fn(),
  refreshSession: vi.fn(),
}));

vi.mock("@/shared/lib/supabase", () => ({
  supabase: {
    auth: { getSession, refreshSession },
  },
}));

import { apiClient, setApiAccessToken } from "@/shared/api/client";

describe("apiClient authentication", () => {
  beforeEach(() => {
    getSession.mockReset();
    refreshSession.mockReset();
    setApiAccessToken(null);
    vi.unstubAllGlobals();
  });

  it("dùng ngay token vừa được AuthProvider đồng bộ", async () => {
    const authorizationHeaders: string[] = [];
    setApiAccessToken("fresh-login-token");
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      authorizationHeaders.push((init.headers as Record<string, string>).Authorization);
      return Promise.resolve(new Response(JSON.stringify({ data: [] }), { status: 200 }));
    }));

    await apiClient.get("/api/admin/shops");

    expect(authorizationHeaders).toEqual(["Bearer fresh-login-token"]);
    expect(getSession).not.toHaveBeenCalled();
  });

  it("làm mới token và thử lại đúng một lần khi backend trả 401", async () => {
    const authorizationHeaders: string[] = [];
    setApiAccessToken("stale-token");
    refreshSession.mockResolvedValue({
      data: { session: { access_token: "refreshed-token" } },
      error: null,
    });
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
      authorizationHeaders.push((init.headers as Record<string, string>).Authorization);
      const status = authorizationHeaders.length === 1 ? 401 : 200;
      const body = status === 401
        ? { detail: "Token khong hop le", status }
        : { data: [] };
      return Promise.resolve(new Response(JSON.stringify(body), { status }));
    }));

    await apiClient.get("/api/admin/shops");

    expect(refreshSession).toHaveBeenCalledTimes(1);
    expect(authorizationHeaders).toEqual([
      "Bearer stale-token",
      "Bearer refreshed-token",
    ]);
  });
});
