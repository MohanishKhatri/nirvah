import type { Metadata } from "next";
import type { ReactNode } from "react";
import Providers from "@/components/Providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "NIRVAH",
  description:
    "Policy-native approval workflows. Describe what you need; NIRVAH reads the policy and builds the approval chain.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-base text-body">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
