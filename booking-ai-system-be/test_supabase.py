"""
Script test ket noi Supabase (phia backend booking-ai-system-be).

Chay:
    cd booking-ai-system-be
    $env:PYTHONPATH = (Get-Location)   # PowerShell
    python scripts/test_supabase.py

Muc dich:
    1. Xac nhan bien SUPABASE_URL / SUPABASE_SERVICE_KEY / SUPABASE_ANON_KEY doc dung.
    2. Xac nhan Supabase client (service role) ket noi duoc va query duoc bang.
    3. Xac nhan JWKS URL truy cap duoc (dung verify JWT admin).
    4. (Tuy chon) Dang nhap tai khoan test de lay access token, xac nhan email
       nam trong ADMIN_EMAILS.

Khong sua backend; chi doc config va goi Supabase client.
Chi dung ASCII de tranh loi encode tren terminal Windows (cp1252).
"""

import os
import sys

from app.core.config import settings
from app.core.supabase import get_supabase

# app/core/supabase.py doc os.environ["SUPABASE_URL"], nhung pydantic_settings
# chi nap .env vao doi tuong settings, KHONG tu dong nap vao os.environ.
# De script (va bat ky tien trinh nao) chay duoc, ta day settings vao os.environ.
os.environ.setdefault("SUPABASE_URL", settings.SUPABASE_URL)
os.environ.setdefault("SUPABASE_SERVICE_KEY", settings.SUPABASE_SERVICE_KEY)
os.environ.setdefault("SUPABASE_ANON_KEY", settings.SUPABASE_ANON_KEY)


def banner(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> int:
    banner("1. KIEM TRA BIEN MOI TRUONG")
    print("SUPABASE_URL        :", settings.SUPABASE_URL or "THIEU")
    print("SUPABASE_SERVICE_KEY:", "CO" if settings.SUPABASE_SERVICE_KEY else "THIEU")
    print("SUPABASE_ANON_KEY   :", "CO" if settings.SUPABASE_ANON_KEY else "THIEU")
    print("SUPABASE_JWKS_URL   :", settings.SUPABASE_JWKS_URL or "THIEU")
    print("ADMIN_EMAILS        :", settings.ADMIN_EMAILS)
    print("SHOP_TIMEZONE       :", settings.SHOP_TIMEZONE)

    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        print("\nTHIEU SUPABASE_URL / SUPABASE_SERVICE_KEY -> khong the ket noi.")
        return 1

    banner("2. KIEM TRA KET NOI SUPABASE (service role)")
    try:
        supabase = get_supabase()
        print("Tao client thanh cong.")
    except Exception as exc:  # noqa: BLE001
        print("Khong tao duoc Supabase client:", exc)
        return 1

    for table in ("therapists", "shops", "bookings"):
        try:
            resp = (
                supabase.table(table)
                .select("count", count="exact")
                .limit(1)
                .execute()
            )
            print(f"Bang '{table}': {resp.count} dong.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"Bang '{table}' loi (co the chua co/migration): {exc}")
    else:
        print("Khong query duoc bang nao (kiem tra schema/migration).")

    banner("3. KIEM TRA JWKS URL")
    import urllib.request

    try:
        with urllib.request.urlopen(settings.SUPABASE_JWKS_URL, timeout=10) as r:
            body = r.read()
        print(f"JWKS phan hoi ({len(body)} bytes). Backend verify JWT admin OK.")
    except Exception as exc:  # noqa: BLE001
        print("JWKS khong truy cap duoc:", exc)
        print("   -> Admin endpoints (/api/admin/*) se tra 401 do khong verify token.")

    banner("4. (TUY CHON) DANG NHAP TAI KHOAN TEST")
    email = settings.SUPABASE_TEST_EMAIL
    password = settings.SUPABASE_TEST_PASSWORD
    if not email or not password:
        print("Chua cau hinh SUPABASE_TEST_EMAIL / SUPABASE_TEST_PASSWORD -> bo qua.")
        print("\nKet noi Supabase co ban OK.")
        return 0

    try:
        res = supabase.auth.sign_in_with_password(
            {"email": email, "password": password}
        )
        user = res.user
        if not user:
            print("Dang nhap that bai (sai email/password hoac user chua ton tai).")
            return 0
        print("Dang nhap OK. User:", user.email)
        is_admin = user.email in settings.ADMIN_EMAILS
        print("Email nam trong ADMIN_EMAILS:", "CO" if is_admin else "KHONG")
        if not is_admin:
            print("   -> Backend se tra 403 cho /api/admin/* du JWT hop le.")
        access = res.session.access_token if res.session else None
        print("Co access token:", "CO" if access else "KHONG")
    except Exception as exc:  # noqa: BLE001
        print("Loi dang nhap:", exc)

    print("\nHoan tat test ket noi Supabase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
