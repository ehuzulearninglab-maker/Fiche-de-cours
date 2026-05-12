import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-geist-sans",
});

export const metadata: Metadata = {
  title: "CV2Portfolio AI — Transform Your CV Into a Premium Portfolio",
  description:
    "Upload your CV and instantly get a beautiful, professional portfolio website powered by AI. The future of personal branding.",
  keywords: ["portfolio", "CV", "resume", "AI", "generator", "website"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} dark`}>
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
