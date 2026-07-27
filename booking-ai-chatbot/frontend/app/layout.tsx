import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Komorebi Tokyo — Wellness Concierge",
  description: "Trợ lý đặt lịch chăm sóc sức khỏe Komorebi Tokyo",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
