import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Komorebi Spa | Massage & AI Concierge",
  description: "Landing page massage/spa với trợ lý AI Kori hỗ trợ tư vấn và đặt lịch.",
};

// Root layout của Next.js, khai báo ngôn ngữ tiếng Việt cho toàn bộ chatbot landing.
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
