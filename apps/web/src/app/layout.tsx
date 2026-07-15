import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Jacaranda Research OS",
  description: "Bilingual, source-grounded equity research.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-AU">
      <body>{children}</body>
    </html>
  );
}
