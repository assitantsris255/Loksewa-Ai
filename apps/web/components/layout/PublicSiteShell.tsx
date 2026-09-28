"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { Footer } from "@/components/layout/footer";
import { Navbar } from "@/components/layout/navbar";

const PUBLIC_EXACT_ROUTES = new Set([
  "/",
  "/contact",
  "/exams",
  "/faqs",
  "/features",
  "/notes",
  "/play-and-earn",
  "/practice",
  "/privacy",
  "/refund",
  "/syllabus",
  "/terms",
]);

const PUBLIC_ROUTE_PREFIXES = ["/courses", "/marketplace"];

export function PublicSiteShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  const hasPublicChrome =
    PUBLIC_EXACT_ROUTES.has(pathname) ||
    PUBLIC_ROUTE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));

  if (!hasPublicChrome) return children;

  return (
    <>
      <Navbar />
      {children}
      <Footer />
    </>
  );
}