import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Toaster } from "sonner";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Dronan · Mission Control",
  description:
    "Voice-first, memory-augmented, self-evolving multi-agent control tower for medical drone fleets.",
  applicationName: "Dronan",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-dvh bg-canvas text-fg`}
      >
        {children}
        <Toaster
          richColors
          position="top-right"
          toastOptions={{
            style: {
              border: "1px solid var(--color-border)",
              boxShadow: "var(--shadow-2)",
            },
          }}
        />
      </body>
    </html>
  );
}
