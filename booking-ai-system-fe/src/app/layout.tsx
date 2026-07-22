import type { Metadata } from "next";
import "./globals.css";
import { AppProviders } from "@/shared/components/providers";

export const metadata: Metadata = {
  title: "Booking AI System",
  description: "Hệ thống đặt lịch massage",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className="h-full antialiased">
      <body className="h-full overflow-hidden font-sans">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
