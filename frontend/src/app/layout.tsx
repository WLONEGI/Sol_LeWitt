import type { Metadata } from "next";
import { DM_Sans, Noto_Sans_JP, JetBrains_Mono, Libre_Baskerville, Noto_Serif_JP } from "next/font/google";

import "./globals.css";
import { ThemeProvider } from "@/providers/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/providers/auth-provider";

const dmSans = DM_Sans({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-dm-sans",
});

const notoSansJP = Noto_Sans_JP({
  weight: ["400", "500", "600", "700"],
  preload: false,
  variable: "--font-noto-sans-jp",
});

const jetbrainsMono = JetBrains_Mono({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

const libreBaskerville = Libre_Baskerville({
  weight: ["400", "700"],
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-libre-baskerville",
});

const notoSerifJP = Noto_Serif_JP({
  weight: ["400", "500", "600", "700"],
  preload: false,
  variable: "--font-noto-serif-jp",
});

export const metadata: Metadata = {
  title: "AI Slide Generator",
  description: "Generate beautiful slides with AI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${dmSans.variable} ${notoSansJP.variable} ${jetbrainsMono.variable} ${libreBaskerville.variable} ${notoSerifJP.variable} antialiased font-sans`}
        suppressHydrationWarning
      >
        <AuthProvider>
          <ThemeProvider
            attribute="class"
            defaultTheme="system"
            enableSystem
            disableTransitionOnChange
          >
            <TooltipProvider>
              {children}
            </TooltipProvider>
          </ThemeProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
