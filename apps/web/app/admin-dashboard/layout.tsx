// @ts-nocheck
"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { RetryImage } from "@/components/ui/retry-image";
import { NotificationBell } from "@/components/layout/notification-bell";
import { Toaster } from "react-hot-toast";
import {
  LayoutDashboard,
  Users,
  GraduationCap,
  BookOpen,
  ClipboardCheck,
  Store,
  Gamepad2,
  BarChart3,
  Settings,
  ShieldAlert,
  Hourglass,
  Database,
  FileText,
  Brain,
  Menu,
  X,
  Layers,
  Bell,
  LogOut,
  Search,
  ChevronRight,
  Sparkles,
  ListTodo,
  CalendarDays,
  LifeBuoy,
  ClipboardList,
  Trophy,
  Quote,
  ShieldCheck,
  Globe,
  Package,
  Bookmark,
  Loader2,
} from "lucide-react";

// ===== Sidebar Nav Config =====
interface NavItem {
  title: string;
  href: string;
  icon: React.ElementType;
  exact?: boolean;
}

interface NavSection {
  title: string;
  items: NavItem[];
}

const SIDEBAR_NAV: NavSection[] = [
  {
    title: "Overview",
    items: [
      { title: "Dashboard", href: "/admin-dashboard", icon: LayoutDashboard as any, exact: true },
    ],
  },
  {
    title: "User & Access",
    items: [
      { title: "Users", href: "/admin-dashboard/users", icon: Users as any },
      { title: "Pending Verification", href: "/admin-dashboard/students/pending-verification", icon: Hourglass as any },
      { title: "Applications", href: "/admin-dashboard/applications", icon: ClipboardCheck },
      { title: "Administrators", href: "/admin-dashboard/admins", icon: ShieldAlert },
      { title: "Roles", href: "/admin-dashboard/roles", icon: Database },
      { title: "Permissions", href: "/admin-dashboard/permissions", icon: Settings as any },
    ],
  },
  {
    title: "Academic",
    items: [
      { title: "Academic Management", href: "/admin-dashboard/academic", icon: GraduationCap as any },
      { title: "Objective Question Bank", href: "/admin-dashboard/academic/questions", icon: BookOpen as any },
      { title: "Subjective Question Bank", href: "/admin-dashboard/academic/subjective-sets", icon: FileText as any },
      { title: "Review Queue", href: "/admin-dashboard/questions/review", icon: ClipboardCheck },
      { title: "Collections", href: "/admin-dashboard/academic/collections", icon: ListTodo },
      { title: "Question Sets", href: "/admin-dashboard/academic/question-sets", icon: Layers },
      { title: "Study Plans", href: "/admin-dashboard/study-plans", icon: CalendarDays },
      { title: "Syllabus", href: "/admin-dashboard/study-materials?section=syllabus", icon: FileText as any },
      { title: "Notes", href: "/admin-dashboard/study-materials", icon: Bookmark as any },
    ],
  },
  {
    title: "Exams",
    items: [
      { title: "Exams & Mock Tests", href: "/admin-dashboard/exams", icon: FileText },
      { title: "Exam Schedule", href: "/admin-dashboard/exams/schedules", icon: CalendarDays },
      { title: "Rankings & Leaderboards", href: "/admin-dashboard/rankings", icon: Trophy },
    ],
  },

  {
    title: "Platform",
    items: [
      { title: "Notifications", href: "/admin-dashboard/notifications", icon: Bell },
      { title: "Community", href: "/admin-dashboard/community", icon: Users as any },
      { title: "Testimonials", href: "/admin-dashboard/testimonials", icon: Quote },
      { title: "Website Content", href: "/admin-dashboard/website-content", icon: Globe },
      { title: "Help & Support", href: "/admin-dashboard/support", icon: LifeBuoy },
      { title: "AI Tutor", href: "/admin-dashboard/ai-tutor", icon: Brain },
      { title: "Marketplace", href: "/admin-dashboard/marketplace", icon: Store },
      { title: "Trust & Safety", href: "/admin-dashboard/marketplace/trust", icon: ShieldCheck },
      { title: "Packages", href: "/admin-dashboard/packages", icon: Package },
      { title: "Evaluations", href: "/admin-dashboard/evaluations", icon: ClipboardCheck },
      { title: "Games", href: "/admin-dashboard/games", icon: Gamepad2 },
    ],
  },
  {
    title: "System",
    items: [
      { title: "Audit Logs", href: "/admin-dashboard/audit-logs", icon: ClipboardList },
      { title: "Analytics", href: "/admin-dashboard/analytics", icon: BarChart3 },
      { title: "Settings", href: "/admin-dashboard/settings", icon: Settings as any },
    ],
  },
];

// SidebarNavItem is defined at module level — outside AdminSidebar — so
// React never sees a new component type on sidebar re-renders (collapse
// toggle, pathname change, mobile open), which would force unmount+remount
// of all 30 nav items on every interaction.
function SidebarNavItem({
  item,
  active,
  pending,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  pending: boolean;
  collapsed: boolean;
  onNavigate: (event: React.MouseEvent<HTMLAnchorElement>, href: string) => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={(event) => onNavigate(event, item.href)}
      title={collapsed ? item.title : undefined}
      aria-current={active ? "page" : undefined}
      aria-busy={pending || undefined}
      className={cn(
        "flex items-center gap-3 rounded-[8px] px-3 py-2.5 text-[13.5px] font-medium transition-all duration-150",
        active
          ? "bg-white/10 text-white shadow-[inset_3px_0_0_0_#D4A72C]"
          : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
        collapsed && "justify-center px-2"
      )}
    >
      <item.icon
        className={cn("shrink-0 h-[18px] w-[18px]", active ? "text-[#D4A72C]" : "text-slate-400")}
        strokeWidth={active ? 2 : 1.5}
      />
      {!collapsed && <span className="truncate">{item.title}</span>}
      {pending && (
        <span role="status" aria-label={`Opening ${item.title}`} className={cn("shrink-0", collapsed ? "" : "ml-auto")}>
          <Loader2 className="h-3.5 w-3.5 animate-spin text-[#D4A72C]" aria-hidden="true" />
          <span className="sr-only">Opening {item.title}</span>
        </span>
      )}
      {!collapsed && active && !pending && (
        <ChevronRight className="ml-auto h-3.5 w-3.5 text-slate-400" />
      )}
    </Link>
  );
}

// ===== Sidebar Component =====
function AdminSidebar({
  collapsed,
  setCollapsed,
  mobileOpen,
  setMobileOpen,
}: {
  collapsed: boolean;
  setCollapsed: (v: boolean) => void;
  mobileOpen: boolean;
  setMobileOpen: (v: boolean) => void;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pendingHref, setPendingHref] = useState<string | null>(null);
  const pendingHrefRef = useRef<string | null>(null);

  const handleNavigation = (event: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      event.currentTarget.target === "_blank"
    ) {
      onMobileClose();
      return;
    }

    const currentRoute = `${pathname}${searchParams.toString() ? `?${searchParams.toString()}` : ""}`;
    if (href === currentRoute) {
      pendingHrefRef.current = null;
      setPendingHref(null);
      onMobileClose();
      return;
    }

    if (pendingHrefRef.current === href) {
      event.preventDefault();
      return;
    }

    pendingHrefRef.current = href;
    setPendingHref(href);
  };

  useEffect(() => {
    if (!pendingHref) return;
    const [hrefPath, hrefQuery] = pendingHref.split("?");
    const currentQuery = searchParams.toString();
    const destinationReached = pathname === hrefPath && (
      hrefQuery === undefined ||
      currentQuery === hrefQuery ||
      currentQuery.includes(hrefQuery)
    );

    if (destinationReached) {
      pendingHrefRef.current = null;
      setPendingHref(null);
      setMobileOpen(false);
    }
  }, [pathname, searchParams, pendingHref, setMobileOpen]);

  // Find the single best matching nav item based on specificity:
  // 1. Matches with exact query parameters take highest priority.
  // 2. Otherwise, the longest matching path prefix wins (so /admin-dashboard/academic/questions
  //    matches Question Bank rather than also highlighting Academic Management).
  const activeItem = useMemo(() => {
    const pendingItem = SIDEBAR_NAV.flatMap(section => section.items).find(item => item.href === pendingHref);
    if (pendingItem) return pendingItem;

    let bestItem: NavItem | null = null;
    let bestScore = -1;

    for (const section of SIDEBAR_NAV) {
      for (const item of section.items) {
        const [hrefPath, hrefQuery] = item.href.split("?");

        if (hrefQuery !== undefined) {
          const searchParamsString = searchParams.toString();
          if (pathname === hrefPath && (searchParamsString === hrefQuery || searchParamsString.includes(hrefQuery))) {
            const score = 10000 + hrefPath.length;
            if (score > bestScore) {
              bestScore = score;
              bestItem = item;
            }
          }
        } else {
          let matches = false;
          if (item.exact) {
            matches = pathname === hrefPath;
          } else {
            matches = pathname === hrefPath || pathname.startsWith(hrefPath + "/");
          }

          if (matches) {
            const score = hrefPath.length;
            if (score > bestScore) {
              bestScore = score;
              bestItem = item;
            }
          }
        }
      }
    }

    return bestItem;
  }, [pathname, searchParams, pendingHref]);


  const sidebarContent = (
    <>
      {/* Logo + Collapse Toggle */}
      <div className="flex h-[60px] items-center justify-between px-4 border-b border-white/10 shrink-0">
        {!collapsed && (
          <Link href="/admin-dashboard" className="flex items-center gap-2.5">
            <div className="bg-[#D4A72C] text-[#0B2545] p-1.5 rounded-[7px]">
              <BookOpen className="h-4 w-4" strokeWidth={2.5} />
            </div>
            <div className="leading-none">
              <span className="font-[800] text-[17px] tracking-tight text-white">
                Loksewa<span className="text-[#D4A72C]">AI</span>
              </span>
              <p className="text-[10px] font-semibold text-white/35 uppercase tracking-widest mt-0.5">
                Admin
              </p>
            </div>
          </Link>
        )}
        {collapsed && (
          <div className="mx-auto bg-[#D4A72C] text-[#0B2545] p-1.5 rounded-[7px]">
            <BookOpen className="h-4 w-4" strokeWidth={2.5} />
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden md:flex items-center justify-center h-7 w-7 rounded-md text-white/40 hover:text-white hover:bg-white/10 transition-colors"
          aria-label="Toggle sidebar"
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <Menu className="h-4 w-4" />
          )}
        </button>
        <button
          onClick={() => setMobileOpen(false)}
          className="md:hidden flex items-center justify-center h-7 w-7 rounded-md text-white/40 hover:text-white hover:bg-white/10 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Navigation */}
      <ScrollArea className="flex-1 py-4">
        <div className={cn("space-y-5 px-3", collapsed && "px-2")}>
          {SIDEBAR_NAV.map((section, idx) => (
            <div key={idx}>
              {!collapsed && (
                <p className="px-3 text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1.5">
                  {section.title}
                </p>
              )}
              {collapsed && idx > 0 && <div className="my-2 border-t border-white/10" />}
              <nav className="space-y-0.5">
                {section.items.map((item) => (
                  <SidebarNavItem
                    key={item.href}
                    item={item}
                    active={activeItem?.href === item.href}
                    pending={pendingHref === item.href}
                    collapsed={collapsed}
                    onNavigate={handleNavigation}
                  />
                ))}
              </nav>
            </div>
          ))}
        </div>
      </ScrollArea>
    </>
  );

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden md:flex flex-col bg-[#0B2545] border-r border-white/10 transition-all duration-300 shrink-0 sticky top-0 h-screen",
          collapsed ? "w-16" : "w-64"
        )}
      >
        {sidebarContent}
      </aside>

      {/* Mobile sidebar */}
      <aside
        className={cn(
          "fixed top-0 left-0 z-50 flex md:hidden flex-col bg-[#0B2545] h-screen w-72 transition-transform duration-300 ease-in-out shadow-2xl",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {sidebarContent}
      </aside>
    </>
  );
}

// ===== Header Component =====
function AdminHeader({
  user,
  onMobileMenuOpen,
}: {
  user: { name: string; email: string; role: string; avatar?: string | null };
  onMobileMenuOpen: () => void;
}) {
  const router = useRouter();
  const { logout } = useAuth();

  const handleAdminLogout = () => {
    logout("/login");
  };

  const initials = user.name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <header className="h-[60px] bg-white border-b border-slate-200 flex items-center px-4 gap-3 sticky top-0 z-30 shrink-0">
      {/* Mobile hamburger */}
      <button
        onClick={onMobileMenuOpen}
        className="md:hidden flex items-center justify-center h-9 w-9 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors"
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Search */}
      <div className="flex-1 max-w-sm hidden sm:block">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search..."
            className="w-full pl-9 pr-4 py-2 text-sm bg-slate-100 border border-transparent rounded-lg text-slate-700 placeholder:text-slate-600 placeholder:font-medium focus:outline-none focus:ring-2 focus:ring-[#0B2545]/20 focus:border-[#0B2545]/30 transition"
          />
        </div>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {/* Notifications */}
        <NotificationBell viewAllHref="/admin-dashboard/notifications/inbox" />

        {/* Separator */}
        <div className="h-6 w-px bg-slate-200 mx-1" />

        {/* Admin info */}
        <div className="flex items-center gap-2.5 pl-1">
          <div className="text-right hidden sm:block leading-none">
            <p className="text-[13px] font-semibold text-[#0B2545]">{user.name}</p>
            <p className="text-[11px] text-slate-400 capitalize font-medium">{user.role}</p>
          </div>
          <Avatar className="h-8 w-8 border-2 border-[#D4A72C]/30">
            {user.avatar ? (
              <RetryImage src={user.avatar} alt={user.name} className="aspect-square h-full w-full object-cover" />
            ) : (
              <AvatarFallback className="bg-[#0B2545] text-[#D4A72C] font-bold text-[12px]">
                {initials}
              </AvatarFallback>
            )}
          </Avatar>

          {/* Logout */}
          <button
            onClick={handleAdminLogout}
            className="flex items-center justify-center h-9 w-9 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}

// ===== Main Layout =====
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;
    const hadDark = html.classList.contains("dark");

    html.classList.add("admin-light-scope");
    body.classList.add("admin-light-scope");
    if (hadDark) {
      html.classList.remove("dark");
    }

    return () => {
      html.classList.remove("admin-light-scope");
      body.classList.remove("admin-light-scope");
      if (hadDark) {
        html.classList.add("dark");
      }
    };
  }, []);

  if (loading) {
    return (
      <div className="admin-light-scope min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 border-3 border-[#0B2545] border-t-[#D4A72C] rounded-full animate-spin" />
          <p className="text-sm text-slate-400">Loading admin panel...</p>
        </div>
      </div>
    );
  }

  if (!user) {
    // Not authenticated — redirect to the unified login
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    return (
      <div className="admin-light-scope min-h-screen flex items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 border-3 border-[#0B2545] border-t-[#D4A72C] rounded-full animate-spin" />
          <p className="text-sm text-slate-400">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  if (!["admin", "super-admin"].includes(user.role)) {
    return (
      <div className="admin-light-scope min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center max-w-sm mx-auto px-6">
          <div className="h-20 w-20 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-5">
            <ShieldAlert className="w-10 h-10 text-red-400" />
          </div>
          <h1 className="text-2xl font-bold text-[#0B2545] mb-2">Access Denied</h1>
          <p className="text-slate-500 mb-6 text-sm leading-relaxed">
            You do not have permission to view this page. This area is restricted to administrators only.
          </p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#0B2545] text-white text-sm font-semibold rounded-lg hover:bg-[#163E6C] transition-colors"
          >
            Return to Home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-light-scope flex h-screen bg-slate-50">
      <AdminSidebar
        collapsed={collapsed}
        setCollapsed={setCollapsed}
        mobileOpen={mobileOpen}
        setMobileOpen={setMobileOpen}
      />

      {/* Main area */}
      <div className="flex flex-col flex-1 min-w-0 overflow-x-hidden">
        <AdminHeader
          user={{
            name: user.name || user.email,
            email: user.email,
            role: user.role,
            avatar: user.avatar,
          }}
          onMobileMenuOpen={() => setMobileOpen(true)}
        />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>

      {/* Admin pages call toast.success/toast.error throughout; without this
          mount those calls render nothing and failures look like silence. */}
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: { background: "#0B2545", color: "#fff", fontSize: "14px" },
          success: { iconTheme: { primary: "#D4A72C", secondary: "#0B2545" } },
          error: { duration: 6000, style: { background: "#991B1B", color: "#fff", fontSize: "14px" } },
        }}
      />
    </div>
  );
}
