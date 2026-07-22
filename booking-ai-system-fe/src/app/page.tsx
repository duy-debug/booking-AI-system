import { redirect } from "next/navigation";

// Chuyển route gốc sang màn hình quản trị mặc định, không render thêm giao diện trung gian.
export default function Home() {
  redirect("/admin");
}
