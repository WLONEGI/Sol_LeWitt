import type { Metadata } from "next";
import { Noto_Serif_JP, Courier_Prime } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/providers/theme-provider";
import { TooltipProvider } from "@/components/ui/tooltip";

const notoSerifJP = Noto_Serif_JP({
  weight: ["200", "300", "400", "500", "600", "700", "900"],
  subsets: ["latin"],
  variable: "--font-noto-serif",
});

const courierPrime = Courier_Prime({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-courier-prime",
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
        className={`${notoSerifJP.variable} ${courierPrime.variable} antialiased font-serif`}
        suppressHydrationWarning
      >
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
      </body>
    </html>
  );
}
