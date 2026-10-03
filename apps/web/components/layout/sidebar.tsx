"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  BookOpen, 
  LayoutDashboard, 
  FileText, 
  History, 
  Target, 
  Bookmark, 
  MessageSquare,
  Trophy,
  Settings,
  LogOut,
  Menu,
  X,
  ShoppingBag,
  Gamepad2,
  Users,
  Bell,
  MessageSquarePlus,
  PenTool,
  CreditCard,
  Award
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { RetryImage } from "@/components/ui/retry-image";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/contexts/AuthContext";
import { platformApi, PlatformBranding } from "@/lib/api/platform";

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
  role?: "student" | "teacher" | "admin" | "super-admin";
}

interface NavLinkItem {
  href: string;
  label: string;
  icon: any;
  isActive?: (pathname: string) => boolean;
}

const DEFAULT_BRAND_NAME = "LoksewaAI";

export function Sidebar({ isOpen, setIsOpen, role = "student" }: SidebarProps) {
  const pathname = usePathname();
  const { user: authUser } = useAuth();

  // Use real user if available, fallback to Guest for unauthenticated renders
  const user = authUser ? { name: authUser.name ? authUser.name : authUser.username } : { name: "Guest" };

  // Real platform name/logo from Admin Settings > Platform, not hardcoded.
  const [branding, setBranding] = useState<PlatformBranding | null>(null);
  useEffect(() => {
    platformApi.getBranding().then(setBranding).catch(() => setBranding(null));
  }, []);
  const brandName = branding?.name || DEFAULT_BRAND_NAME;
  // The gold "AI" accent is a deliberate visual treatment for the default
  // brand name; a differently configured name renders as plain text.
  const brandSuffix = brandName.endsWith("AI") ? "AI" : null;
  const brandBase = brandSuffix ? brandName.slice(0, -2) : brandName;

  const studentLinks: NavLinkItem[] = [
    { 
      href: "/student", 
      label: "Dashboard", 
      icon: LayoutDashboard,
      isActive: (p) => p === "/student"
    },
    { 
      href: "/student/learning", 
      label: "My Learning", 
      icon: BookOpen,
      isActive: (p) => 
        p === "/student/learning" || 
        p.startsWith("/student/learning/") || 
        p === "/student/courses" || 
        p.startsWith("/student/courses/") || 
        p === "/student/purchases" || 
        p.startsWith("/student/purchases/")
    },
    { 
      href: "/student/study-plan", 
      label: "My Study Plan", 
      icon: Target,
      isActive: (p) => p === "/student/study-plan" || p.startsWith("/student/study-plan/")
    },
    { 
      href: "/student/syllabus", 
      label: "Syllabus & Notes", 
      icon: BookOpen,
      isActive: (p) => 
        p === "/student/syllabus" || 
        p.startsWith("/student/syllabus/") || 
        p === "/student/notes" || 
        p.startsWith("/student/notes/")
    },
    { 
      href: "/student/practice", 
      label: "Practice", 
      icon: Trophy,
      isActive: (p) => p === "/student/practice" || p.startsWith("/student/practice/")
    },
    { 
      href: "/student/exams", 
      label: "Mock Exams", 
      icon: FileText,
      isActive: (p) => p === "/student/exams" || p.startsWith("/student/exams/")
    },
    { 
      href: "/student/results-feedback", 
      label: "Results & Feedback", 
      icon: Award,
      isActive: (p) => 
        p === "/student/results-feedback" || 
        p.startsWith("/student/results-feedback/") || 
        p === "/student/results" || 
        p.startsWith("/student/results/") || 
        p === "/student/feedback" || 
        p.startsWith("/student/feedback/")
    },
    { 
      href: "/student/leaderboard-analytics", 
      label: "Leaderboard & Analytics", 
      icon: Trophy,
      isActive: (p) => 
        p === "/student/leaderboard-analytics" || 
        p.startsWith("/student/leaderboard-analytics/") || 
        p === "/student/leaderboard" || 
        p.startsWith("/student/leaderboard/") || 
        p === "/student/analytics" || 
        p.startsWith("/student/analytics/")
    },
    { 
      href: "/student/community", 
      label: "Community", 
      icon: Users,
      isActive: (p) => p === "/student/community" || p.startsWith("/student/community/")
    },
    { 
      href: "/student/ai-tutor", 
      label: "AI Tutor", 
      icon: MessageSquare,
      isActive: (p) => p === "/student/ai-tutor" || p.startsWith("/student/ai-tutor/")
    },
    { 
      href: "/student/marketplace", 
      label: "Marketplace", 
      icon: ShoppingBag,
      isActive: (p) => p === "/student/marketplace" || p.startsWith("/student/marketplace/")
    },
    { 
      href: "/student/games", 
      label: "Games", 
      icon: Gamepad2,
      isActive: (p) => p === "/student/games" || p.startsWith("/student/games/")
    },
  ];

  const adminLinks: NavLinkItem[] = [
    { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
    { href: "/admin/mock-exams", label: "Mock Exam Review", icon: FileText },
    { href: "/admin-dashboard/packages", label: "Subscription Plans", icon: Bookmark },
    { href: "/admin/payment-settings", label: "Payment Settings", icon: Settings },
    { href: "/admin-dashboard/applications", label: "Subscription Payments", icon: FileText },
  ];

  const teacherLinksGroups = [
    {
      group: "TEACHING",
      links: [
        { href: "/teacher", label: "Overview", icon: LayoutDashboard },
        { href: "/teacher/courses", label: "My Courses", icon: BookOpen },
        { href: "/teacher/students", label: "Students", icon: Users },
      ]
    },
    {
      group: "CONTENT",
      links: [
        { href: "/teacher/questions", label: "Question Bank", icon: Target },
        { href: "/teacher/practice-sets", label: "Practice Sets", icon: Trophy },
        { href: "/teacher/mock-exams", label: "Mock Exams", icon: FileText },
        { href: "/teacher/study-materials", label: "Study Materials", icon: Bookmark },
      ]
    },
    {
      group: "PERFORMANCE",
      links: [
        { href: "/teacher/evaluations", label: "Evaluations", icon: MessageSquare },
        { href: "/teacher/evaluate", label: "Subjective Exam Grading", icon: PenTool },
        { href: "/teacher/exam-evaluations", label: "Subjective Model Exams", icon: PenTool },
        { href: "/teacher/analytics", label: "Analytics", icon: History },
      ]
    }
  ];

  // Also include notifications which didn't fit the main categories perfectly
  const teacherExtraLinks = [
    { href: "/teacher/notifications", label: "Notifications", icon: Bell },
  ];

  let links = studentLinks;
  if (role === "admin" || role === "super-admin") {
    links = adminLinks;
  } else if (role !== "student" && role !== "teacher") {
    console.warn(`Unknown role "${role}" provided to Sidebar. Falling back to studentLinks.`);
  }

  return (
    <>
      {/* Mobile Overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 z-40 bg-[#0A1118]/80 backdrop-blur-sm lg:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside 
        className={cn(
          "fixed top-0 left-0 z-50 flex h-screen w-72 flex-col bg-[#0B2545] dark:bg-card border-r border-[#163E6B] dark:border-border transition-transform duration-300 ease-in-out lg:translate-x-0 text-white dark:text-foreground",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 items-center justify-between px-6 border-b border-[#163E6B] dark:border-border">
          <Link href="/" className="flex items-center space-x-3">
            {branding?.logoUrl ? (
              <RetryImage src={branding.logoUrl} alt={brandName} className="h-8 w-8 rounded-[8px] object-contain" />
            ) : (
              <div className="bg-[#D4A72C] text-[#0A1118] p-1.5 rounded-[8px]">
                <BookOpen className="h-5 w-5" strokeWidth={2.5} />
              </div>
            )}
            <span className="font-[800] text-[20px] tracking-tight">
              {brandBase}
              {brandSuffix && <span className="text-[#D4A72C]">{brandSuffix}</span>}
            </span>
          </Link>
          <Button variant="ghost" size="icon" className="lg:hidden text-white hover:bg-white/10" onClick={() => setIsOpen(false)}>
            <X className="h-5 w-5" />
          </Button>
        </div>

        <ScrollArea className="flex-1 py-6 px-4">
          <nav className="space-y-1.5">
            {role === "teacher" ? (
              <>
                {teacherLinksGroups.map((group, idx) => (
                  <div key={group.group} className={cn(idx > 0 && "mt-6")}>
                    <h4 className="text-[11px] font-bold text-slate-400/80 mb-2 px-3 tracking-wider uppercase">
                      {group.group}
                    </h4>
                    <div className="space-y-1">
                      {group.links.map((link) => {
                        const Icon = link.icon;
                        const isActive = pathname === link.href || (link.href !== "/teacher" && pathname.startsWith(`${link.href}/`));
                        return (
                          <Link
                            key={link.href}
                            href={link.href}
                            onClick={() => setIsOpen(false)}
                            className={cn(
                              "flex items-center gap-3 rounded-[8px] px-3 py-2.5 text-[14px] font-medium transition-all duration-200",
                              isActive 
                                ? "bg-white/10 text-white shadow-[inset_3px_0_0_0_#D4A72C]" 
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            )}
                          >
                            <Icon 
                              className={cn(
                                "h-[18px] w-[18px] transition-all duration-300", 
                                isActive 
                                  ? "text-[#D4A72C] drop-shadow-[0_0_8px_rgba(212,167,44,0.5)] scale-110" 
                                  : "text-slate-400 group-hover:text-slate-300"
                              )} 
                              strokeWidth={isActive ? 2 : 1.5} 
                            />
                            {link.label}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                ))}
                
                <div className="mt-6">
                  <div className="space-y-1">
                    {teacherExtraLinks.map((link) => {
                      const Icon = link.icon;
                      const isActive = pathname === link.href;
                      return (
                        <Link
                          key={link.href}
                          href={link.href}
                          onClick={() => setIsOpen(false)}
                          className={cn(
                            "flex items-center gap-3 rounded-[8px] px-3 py-2.5 text-[14px] font-medium transition-all duration-200",
                            isActive 
                              ? "bg-white/10 text-white shadow-[inset_3px_0_0_0_#D4A72C]" 
                              : "text-slate-300 hover:bg-white/5 hover:text-white"
                          )}
                        >
                          <Icon 
                            className={cn(
                              "h-[18px] w-[18px] transition-all duration-300", 
                              isActive 
                                ? "text-[#D4A72C] drop-shadow-[0_0_8px_rgba(212,167,44,0.5)] scale-110" 
                                : "text-slate-400 group-hover:text-slate-300"
                            )} 
                            strokeWidth={isActive ? 2 : 1.5} 
                          />
                          {link.label}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              links.map((link) => {
                const Icon = link.icon;
                const isActive = link.isActive
                  ? link.isActive(pathname)
                  : pathname === link.href || (link.href !== `/${role}` && pathname.startsWith(`${link.href}/`));
                
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setIsOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-[8px] px-3 py-2.5 text-[14px] font-medium transition-all duration-200",
                      isActive 
                        ? "bg-white/10 text-white dark:bg-primary/10 dark:text-foreground shadow-[inset_2px_0_0_0_#D4A72C]" 
                        : "text-slate-300 dark:text-muted-foreground hover:bg-white/5 dark:hover:bg-muted/50 hover:text-white dark:hover:text-foreground"
                    )}
                  >
                    <Icon 
                      className={cn(
                        "h-[18px] w-[18px] transition-all duration-300", 
                        isActive 
                          ? "text-[#D4A72C] drop-shadow-[0_0_8px_rgba(212,167,44,0.5)] scale-110" 
                          : "text-slate-400 dark:text-muted-foreground group-hover:text-slate-300 dark:group-hover:text-foreground"
                      )} 
                      strokeWidth={isActive ? 2 : 1.5} 
                    />
                    {link.label}
                  </Link>
                );
              })
            )}
          </nav>
        </ScrollArea>

        <div className="border-t border-[#163E6B] dark:border-border p-4 flex flex-col gap-1">
          {(() => {
            const isSettingsActive = pathname === `/${role}/settings` || pathname.startsWith(`/${role}/settings/`);
            const isHelpActive = pathname === `/${role}/help-support` || pathname.startsWith(`/${role}/help-support/`) || pathname === `/${role}/help` || pathname.startsWith(`/${role}/help/`);
            return (
              <>
                <Link
                  href={`/${role}/settings`}
                  onClick={() => setIsOpen(false)}
                  className={cn(
                    "flex items-center gap-3 rounded-[8px] px-3 py-2.5 text-[13px] font-medium transition-all duration-200",
                    isSettingsActive 
                      ? "bg-white/10 text-white dark:bg-primary/10 dark:text-foreground shadow-[inset_2px_0_0_0_#D4A72C]" 
                      : "text-slate-300 dark:text-muted-foreground hover:bg-white/5 dark:hover:bg-muted/50 hover:text-white dark:hover:text-foreground"
                  )}
                >
                  <Settings 
                    className={cn(
                      "h-[18px] w-[18px] transition-all duration-300", 
                      isSettingsActive 
                        ? "text-[#D4A72C] drop-shadow-[0_0_8px_rgba(212,167,44,0.5)] scale-110" 
                        : "text-slate-400 dark:text-muted-foreground group-hover:text-slate-300 dark:group-hover:text-foreground"
                    )} 
                    strokeWidth={isSettingsActive ? 2 : 1.5} 
                  />
                  Settings
                </Link>
                <Link
                  href={`/${role}/help-support`}
                  onClick={() => setIsOpen(false)}
                  className={cn(
                    "flex items-center gap-3 rounded-[8px] px-3 py-2.5 text-[13px] font-medium transition-all duration-200 mb-2",
                    isHelpActive 
                      ? "bg-white/10 text-white dark:bg-primary/10 dark:text-foreground shadow-[inset_2px_0_0_0_#D4A72C]" 
                      : "text-slate-300 dark:text-muted-foreground hover:bg-white/5 dark:hover:bg-muted/50 hover:text-white dark:hover:text-foreground"
                  )}
                >
                  <MessageSquare 
                    className={cn(
                      "h-[18px] w-[18px] transition-all duration-300", 
                      isHelpActive 
                        ? "text-[#D4A72C] drop-shadow-[0_0_8px_rgba(212,167,44,0.5)] scale-110" 
                        : "text-slate-400 dark:text-muted-foreground group-hover:text-slate-300 dark:group-hover:text-foreground"
                    )} 
                    strokeWidth={isHelpActive ? 2 : 1.5} 
                  />
                  Help & Support
                </Link>
              </>
            );
          })()}

          <div className="flex items-center gap-3 bg-white/5 p-3 rounded-[12px] border border-white/10 mt-2">
            <Avatar className="h-10 w-10 border border-[#D4A72C]/30 bg-[#0A1118]">
              <RetryImage src={authUser?.avatar || "/images/profile.png"} alt={user.name} className="aspect-square h-full w-full object-cover" />
            </Avatar>
            <div className="flex flex-col overflow-hidden">
              <span className="text-[13px] font-bold text-white dark:text-foreground truncate">{user.name}</span>
              <span className="text-[11px] font-medium text-slate-400 dark:text-muted-foreground truncate capitalize">
                {authUser?.role?.replace("-", " ") || "User"}
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
