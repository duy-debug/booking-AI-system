// Hiển thị trang chào tổng quan và hướng người dùng đến các phân hệ trong sidebar.
export default function AdminHomePage() {
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold text-zinc-900">Tổng quan</h1>
      <p className="text-zinc-500">
        Chào mừng đến hệ thống quản trị booking. Chọn mục bên trái để bắt đầu.
      </p>
    </div>
  );
}
