import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Komorebi Spa | Massage & AI Concierge",
  description: "Landing page massage/spa với trợ lý AI Kori hỗ trợ tư vấn và đặt lịch.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
