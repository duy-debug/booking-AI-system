import os
from supabase import create_client, Client

_supabase: Client | None = None


# Khởi tạo Supabase service client theo kiểu singleton để tránh tạo lại kết nối cho mỗi lần sử dụng.
def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _supabase = create_client(url, key)
    return _supabase
