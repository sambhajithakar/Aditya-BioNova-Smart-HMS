import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { LangProvider } from "@/lib/lang";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aditya BioNova Smart HMS",
  description: "Multi-tenant clinic & hospital management.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Reading the request headers opts every route into dynamic rendering,
  // which the nonce-based CSP requires (a static page has no per-request
  // nonce). Next picks the nonce up from the CSP request header set by
  // middleware.ts and stamps it on its scripts.
  await headers();
  return (
    <html lang="en">
      <body>
        <LangProvider>{children}</LangProvider>
      </body>
    </html>
  );
}
