import { AdminShell } from "@/features/auth/AdminShell";

// Bao bọc mọi trang quản trị bằng shell xác thực, sidebar cố định và vùng nội dung cuộn riêng.
export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AdminShell>{children}</AdminShell>;
}
