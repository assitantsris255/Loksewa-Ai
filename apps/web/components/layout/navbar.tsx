"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  BookOpen, Menu, X, Moon, Sun, ArrowRight,
  Home, Target, FileText, Sparkles, ShoppingBag, Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "next-themes";

export function Navbar() {
  const pathname = usePathname();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
  const [isScrolled, setIsScrolled] = React.useState(false);
  const [pendingHref, setPendingHref] = React.useState<string | null>(null);
  const pendingHrefRef = React.useRef<string | null>(null);
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  const handleNavigation = (
    event: React.MouseEvent<HTMLAnchorElement>,
    href: string
  ) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.currentTarget.target === "_blank"
    ) return;

    if (href === pathname && pendingHrefRef.current === null) {
      setIsMobileMenuOpen(false);
      return;
    }

    if (pendingHrefRef.current === href) {
      event.preventDefault();
      return;
    }

    pendingHrefRef.current = href;
    setPendingHref(href);
  };

  React.useEffect(() => {
    setMounted(true);
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // Close mobile menu on route change
  React.useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [pathname]);

  React.useEffect(() => {
    if (pendingHref !== pathname) return;
    pendingHrefRef.current = null;
    setPendingHref(null);
  }, [pathname, pendingHref]);

  React.useEffect(() => {
    const clearPendingNavigation = () => {
      pendingHrefRef.current = null;
      setPendingHref(null);
    };
    window.addEventListener("popstate", clearPendingNavigation);
    return () => window.removeEventListener("popstate", clearPendingNavigation);
  }, []);

  const navLinks = [
    { href: "/", label: "Home" },
    { href: "/courses", label: "Courses" },
    { href: "/syllabus", label: "Syllabus" },
    { href: "/features", label: "Features" },
    { href: "/play-and-earn", label: "Play & Earn" },
    { href: "/marketplace", label: "Marketplace" },
    { href: "/faqs", label: "FAQs" },
  ];

  // Bottom tab bar — mobile only. Four real destinations plus a "Menu" tab
  // that reuses the existing hamburger drawer instead of duplicating it.
  const mobileTabs = [
    { href: "/", label: "Home", icon: Home },
    { href: "/courses", label: "Courses", icon: BookOpen },
    { href: "/features", label: "Features", icon: Sparkles },
    { href: "/marketplace", label: "Marketplace", icon: ShoppingBag },
  ];

  return (
    <>
      {/* Fixed wrapper is full-width and non-interactive; the actual bar
          floats inside it with margin on every side so it reads as a
          suspended capsule rather than a bar glued to the viewport edge. */}
      <header className="fixed top-0 left-0 w-full z-50 pointer-events-none">
        <div className="pointer-events-auto mx-auto max-w-[1400px] px-4 sm:px-6 lg:px-8 pt-3 sm:pt-4">
          <div
            className={`flex items-center justify-between gap-3 rounded-full border transition-all duration-500 ${
              isScrolled
                ? "px-3 py-2 bg-white/85 dark:bg-[#04080F]/90 backdrop-blur-xl border-slate-200/70 dark:border-white/[0.08] shadow-[0_10px_36px_-8px_rgba(11,37,69,0.16)] dark:shadow-[0_10px_36px_-8px_rgba(0,0,0,0.6)]"
                : "px-3 py-2.5 bg-white/55 dark:bg-white/[0.02] backdrop-blur-md border-white/40 dark:border-white/[0.04] shadow-[0_4px_20px_-8px_rgba(11,37,69,0.08)]"
            }`}
          >

            {/* ── Brand ────────────────────────────── */}
            <Link href="/" onClick={(event) => handleNavigation(event, "/")} className="flex items-center gap-2.5 group shrink-0 pl-1">
              <div className="p-1.5 rounded-[9px] bg-gradient-to-br from-[#163E6B] to-[#0B2545] shadow-[0_2px_10px_rgba(11,37,69,0.25)] transition-transform duration-300 group-hover:scale-105 group-hover:rotate-[-3deg]">
                <BookOpen className="h-5 w-5 text-[#D4A72C]" strokeWidth={2.5} />
              </div>
              <span className="font-[800] text-[19px] tracking-tight text-slate-900 dark:text-white hidden sm:inline">
                Loksewa<span className="text-[#D4A72C]">AI</span>
              </span>
            </Link>

            {/* ── Desktop Navigation — pill segment with a sliding active indicator ── */}
            <nav className="hidden lg:flex items-center gap-0.5 bg-slate-900/[0.04] dark:bg-white/[0.05] rounded-full p-1">
              {navLinks.map((link) => {
                const isActive = pathname === link.href;
                const isPending = pendingHref === link.href;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={(event) => handleNavigation(event, link.href)}
                    aria-current={isActive ? "page" : undefined}
                    aria-busy={isPending || undefined}
                    className={`relative px-3.5 py-1.5 rounded-full text-[13px] font-[600] tracking-wide cursor-pointer ${isPending ? "bg-white/60 dark:bg-white/10" : ""}`}
                  >
                    {(isActive || isPending) && (
                      <motion.span
                        layoutId="nav-active-pill"
                        className={`absolute inset-0 rounded-full shadow-[0_2px_10px_rgba(11,37,69,0.1)] ${isPending ? "bg-white/70 dark:bg-white/10" : "bg-white dark:bg-white/10"}`}
                        transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      />
                    )}
                    <span
                      className={`relative z-10 flex items-center gap-1.5 transition-colors duration-200 ${
                        isActive || isPending
                          ? "text-slate-900 dark:text-white"
                          : "text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-white"
                      }`}
                    >
                      {link.label}
                      {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin text-[#C29322]" aria-hidden="true" />}
                    </span>
                    {isPending && <span className="sr-only" role="status">Opening {link.label}</span>}
                  </Link>
                );
              })}
            </nav>

            {/* ── Desktop Actions ──────────────────── */}
            <div className="hidden lg:flex items-center gap-2.5 pr-1">
              {/* Theme Toggle */}
              {mounted && (
                <button
                  onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                  className="w-8 h-8 rounded-full flex items-center justify-center text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-900/[0.05] dark:hover:bg-white/8 transition-all"
                  aria-label="Toggle theme"
                >
                  {theme === "dark"
                    ? <Sun className="h-4 w-4" />
                    : <Moon className="h-4 w-4" />
                  }
                </button>
              )}

              {/* Log In - single unified entry point; role-based redirect happens
                  after authentication (see app/login/page.tsx), never via a
                  separate public Teacher/Admin portal link. */}
              <Link
                href="/login"
                onClick={(event) => handleNavigation(event, "/login")}
                className="text-[13px] font-[600] text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors px-1.5"
              >
                Log In
              </Link>

              {/* Get Started */}
              <Link href="/register" onClick={(event) => handleNavigation(event, "/register")}>
                <Button className="btn-gold-gradient text-[#040B14] h-[36px] px-4.5 rounded-full font-[700] text-[13px] border-none flex items-center gap-1.5 group">
                  Get Started
                  <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                </Button>
              </Link>
            </div>

            {/* ── Mobile Hamburger ─────────────────── */}
            <div className="flex lg:hidden items-center gap-1 pr-0.5">
              <Link
                href="/login"
                onClick={(event) => handleNavigation(event, "/login")}
                className="mr-0.5 px-3 py-1.5 rounded-full text-[12px] font-[700] text-slate-700 dark:text-white border border-slate-200/80 dark:border-white/15 hover:bg-slate-900/[0.05] dark:hover:bg-white/8 transition-all"
              >
                Login
              </Link>
              {mounted && (
                <button
                  onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                  className="w-8 h-8 rounded-full flex items-center justify-center text-slate-500 dark:text-slate-400 hover:bg-slate-900/[0.05] dark:hover:bg-white/8 transition-all"
                  aria-label="Toggle theme"
                >
                  {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                </button>
              )}
              <button
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
                className="w-9 h-9 rounded-full flex items-center justify-center text-slate-700 dark:text-white hover:bg-slate-900/[0.05] dark:hover:bg-white/8 transition-all"
                aria-label="Toggle menu"
              >
                {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
            </div>
          </div>

          {/* ── Mobile Navigation Drawer — its own floating card below the bar ── */}
          <div className={`lg:hidden overflow-hidden transition-all duration-500 ease-in-out ${
            isMobileMenuOpen ? "max-h-[600px] opacity-100 mt-2" : "max-h-0 opacity-0 mt-0"
          }`}>
            <div className="rounded-[24px] border border-slate-200/70 dark:border-white/[0.08] bg-white/97 dark:bg-[#04080F]/97 backdrop-blur-2xl shadow-[0_20px_50px_-12px_rgba(11,37,69,0.18)] overflow-hidden">
              <nav className="flex flex-col p-3 gap-1">
                {navLinks.map((link) => {
                  const isActive = pathname === link.href;
                  const isPending = pendingHref === link.href;
                  return (
                    <Link
                      key={link.href}
                      href={link.href}
                      onClick={(event) => handleNavigation(event, link.href)}
                      aria-current={isActive ? "page" : undefined}
                      aria-busy={isPending || undefined}
                      className={`flex items-center justify-between text-[15px] font-[600] px-4 py-3 rounded-[14px] transition-all cursor-pointer ${
                        isActive || isPending
                          ? "bg-slate-100 dark:bg-white/8 text-slate-900 dark:text-white"
                          : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-white/5 hover:text-slate-900 dark:hover:text-white"
                      }`}
                    >
                      <span className="flex items-center">
                        {(isActive || isPending) && <span className="w-1.5 h-1.5 rounded-full bg-[#D4A72C] mr-3 shrink-0" />}
                        {link.label}
                      </span>
                      {isPending && <Loader2 className="h-4 w-4 animate-spin text-[#C29322]" aria-hidden="true" />}
                      {isPending && <span className="sr-only" role="status">Opening {link.label}</span>}
                    </Link>
                  );
                })}
              </nav>

              <div className="h-px bg-slate-100 dark:bg-white/5 mx-3" />

              <div className="p-3 flex flex-col gap-2.5 pb-4">
                {/* Single unified Login entry - role-based redirect happens after
                    authentication (see app/login/page.tsx). */}
                <div className="flex gap-2">
                  <Link href="/login" onClick={(event) => handleNavigation(event, "/login")} className="flex-1">
                    <Button variant="outline" className="w-full h-[44px] text-[14px] font-[600] border-slate-200 dark:border-white/10 text-slate-700 dark:text-white rounded-[14px] bg-transparent">
                      Log In
                    </Button>
                  </Link>
                  <Link href="/register" onClick={(event) => handleNavigation(event, "/register")} className="flex-1">
                    <Button className="btn-gold-gradient w-full h-[44px] text-[14px] font-[700] text-[#040B14] rounded-[14px] border-none">
                      Get Started
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ── Mobile app-style bottom tab bar ──────────────────────────────── */}
      <nav
        className="lg:hidden fixed bottom-0 left-0 right-0 z-50 pb-[env(safe-area-inset-bottom)] bg-white/90 dark:bg-[#04080F]/92 backdrop-blur-2xl border-t border-slate-200/70 dark:border-white/[0.08] shadow-[0_-8px_30px_-12px_rgba(11,37,69,0.18)]"
        aria-label="Primary"
      >
        <div className="grid grid-cols-5 h-[64px]">
          {mobileTabs.map((tab) => {
            const isActive = pathname === tab.href;
            const isPending = pendingHref === tab.href;
            const Icon = tab.icon;
            return (
              <Link
                key={tab.href}
                href={tab.href}
                onClick={(event) => handleNavigation(event, tab.href)}
                aria-current={isActive ? "page" : undefined}
                aria-busy={isPending || undefined}
                className="relative flex flex-col items-center justify-center gap-1 group cursor-pointer"
              >
                {(isActive || isPending) && (
                  <motion.span
                    layoutId="mobile-tab-active"
                    className="absolute top-1.5 w-9 h-1 rounded-full bg-[#D4A72C]"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                {isPending ? (
                  <Loader2 className="w-[21px] h-[21px] animate-spin text-[#C29322] dark:text-[#F0C95A]" aria-hidden="true" />
                ) : (
                  <Icon
                    className={`w-[21px] h-[21px] transition-colors ${
                      isActive ? "text-[#C29322] dark:text-[#F0C95A]" : "text-slate-400 dark:text-slate-500"
                    }`}
                    strokeWidth={isActive ? 2.4 : 2}
                  />
                )}
                <span
                  className={`text-[10px] font-[700] transition-colors ${
                    isActive || isPending ? "text-slate-900 dark:text-white" : "text-slate-400 dark:text-slate-500"
                  }`}
                >
                  {tab.label}
                </span>
                {isPending && <span className="sr-only" role="status">Opening {tab.label}</span>}
              </Link>
            );
          })}

          <button
            onClick={() => setIsMobileMenuOpen((open) => !open)}
            className="relative flex flex-col items-center justify-center gap-1"
            aria-label="Toggle menu"
            aria-expanded={isMobileMenuOpen}
          >
            {isMobileMenuOpen && (
              <motion.span
                layoutId="mobile-tab-active"
                className="absolute top-1.5 w-9 h-1 rounded-full bg-[#D4A72C]"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            )}
            {isMobileMenuOpen ? (
              <X className="w-[21px] h-[21px] text-[#C29322] dark:text-[#F0C95A]" strokeWidth={2.4} />
            ) : (
              <Menu className="w-[21px] h-[21px] text-slate-400 dark:text-slate-500" strokeWidth={2} />
            )}
            <span
              className={`text-[10px] font-[700] transition-colors ${
                isMobileMenuOpen ? "text-slate-900 dark:text-white" : "text-slate-400 dark:text-slate-500"
              }`}
            >
              Menu
            </span>
          </button>
        </div>
      </nav>
    </>
  );
}
