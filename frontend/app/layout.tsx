import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Northstar BI", description: "Your business intelligence workspace" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
