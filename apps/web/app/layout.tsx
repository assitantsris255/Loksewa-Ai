import type { Metadata } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/contexts/AuthContext";
import { FocusModeProvider } from "@/contexts/FocusModeContext";
import { OsDndGuideModal } from "@/components/student/focus/OsDndGuideModal";
import { PublicSiteShell } from "@/components/layout/PublicSiteShell";
import Providers from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["600", "700", "800"],
  variable: "--font-jakarta",
});

export const metadata: Metadata = {
  title: "Loksewa Examination & Learning Ecosystem",
  description:
    "Comprehensive preparation platform for Nepal Public Service Commission examinations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className={`${inter.variable} ${jakarta.variable} font-sans antialiased bg-background text-foreground min-h-screen flex flex-col`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          <Providers>
            <AuthProvider>
              <FocusModeProvider>
                <PublicSiteShell>{children}</PublicSiteShell>
                {/* OS DND guide — appears on every page when Focus Mode is toggled ON */}
                <OsDndGuideModal />
              </FocusModeProvider>
            </AuthProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  );
}
