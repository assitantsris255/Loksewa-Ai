"use client";

import React, { useState, useCallback, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { 
  BookOpen, Target, Clock, Calendar, CheckCircle2, Circle, 
  ChevronRight, Sparkles, MessageSquare, FileText, ArrowRight, TrendingUp,
  ShoppingBag, HelpCircle, Flame, Activity, Gift, Copy, Share2, Users, Coins,
  GraduationCap, AlertCircle, GripVertical, Lock
} from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { RetryImage } from "@/components/ui/retry-image";
import { dashboardApi, QUICK_ACTIONS } from "@/lib/api/dashboard";
import { gamificationService } from "@/lib/api/gamification";
import { notesApi } from "@/lib/api/notes";
import { useAuth } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  UniqueIdentifier,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

import { LoksewaExamCountdown } from "@/components/student/countdown/LoksewaExamCountdown";
import { MockExamCountdown } from "@/components/student/countdown/MockExamCountdown";
import { Skeleton } from "@/components/ui/skeleton";
import { useOptionalStudentContext } from "@/contexts/StudentContext";

// ─── Widget IDs ────────────────────────────────────────────────────────────────
const FULL_WIDTH_WIDGETS = [
  "motivation",
  "quick-actions",
  "continue-study",

  "referral-card",
] as const;

const GRID_WIDGETS = [
  "referrals-list",
  "your-progress",
  "upcoming-exams",
] as const;

type FullWidthId = (typeof FULL_WIDTH_WIDGETS)[number];
type GridId = (typeof GRID_WIDGETS)[number];

const STORAGE_KEY_FULL = "dashboard-full-widget-order";
const STORAGE_KEY_GRID = "dashboard-grid-widget-order";

function loadOrder<T extends string>(key: string, defaults: readonly T[]): T[] {
  if (typeof window === "undefined") return [...defaults];
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "null");
    if (Array.isArray(saved) && saved.every((id) => (defaults as readonly string[]).includes(id))) {
      return saved as T[];
    }
  } catch {}
  return [...defaults];
}

// ─── Sortable Widget Wrapper ───────────────────────────────────────────────────
interface SortableWidgetProps {
  id: string;
  children: React.ReactNode;
  className?: string;
}

function SortableWidget({ id, children, className }: SortableWidgetProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} className={cn("relative group/dnd", className)}>
      {children}
    </div>
  );
}


// Drag overlay ghost card
function WidgetDragGhost({ label }: { label: string }) {
  return (
    <div className="bg-card border-2 border-blue-400 border-dashed rounded-[16px] p-6 shadow-2xl opacity-90 flex items-center gap-3">
      <GripVertical className="w-5 h-5 text-blue-400" />
      <span className="text-sm font-semibold text-muted-foreground">{label}</span>
    </div>
  );
}

export default function StudentDashboardPage() {
  const { user } = useAuth();
  const studentCtx = useOptionalStudentContext();
  const effectiveCourseId = studentCtx?.activeCourse?.id;
  const isCtxLoading = studentCtx?.isLoading ?? false;

  const {
    data,
    isLoading: isDashboardLoading,
    isFetching: dashboardFetching,
    isError,
    refetch: refetchDashboard,
  } = useQuery({
    queryKey: ["student-dashboard", effectiveCourseId ?? null],
    queryFn: () => dashboardApi.getStudentDashboard(effectiveCourseId),
    staleTime: 45 * 1000,
  });
  const loading = !data && (isCtxLoading || isDashboardLoading);
  const error = isError && !data;

  // Background/secondary data - each cached independently so, e.g., a
  // stale referral list doesn't block a fresh analytics overview.
  const { data: motivation } = useQuery({
    // Same quote all day - safe to treat as very stable.
    queryKey: ["daily-motivation"],
    queryFn: () => dashboardApi.getDailyMotivation().catch(() => null),
    staleTime: 10 * 60 * 1000,
  });
  const { data: referralData, refetch: refetchReferral } = useQuery({
    queryKey: ["referral-dashboard"],
    queryFn: () => gamificationService.getStudentReferralDashboard().catch(() => null),
    staleTime: 60 * 1000,
  });
  const { data: referralHistory = [] } = useQuery({
    queryKey: ["referral-history"],
    queryFn: () => gamificationService.getStudentReferralHistory().catch(() => []),
    staleTime: 60 * 1000,
  });

  // Background data warming: once the dashboard itself has rendered, quietly
  // pre-fetch Syllabus data after a 2.5s delay to keep network free for initial render.
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!data) return;
    const timer = setTimeout(() => {
      queryClient.prefetchQuery({
        queryKey: ["syllabus-notes-portal", null],
        queryFn: () => notesApi.getStudentPortalView(undefined),
        staleTime: 5 * 60 * 1000,
      });
    }, 2500);
    return () => clearTimeout(timer);
  }, [data, queryClient]);

  // ── DnD state ──────────────────────────────────────────────────────────────
  const [fullOrder, setFullOrder] = useState<FullWidthId[]>(() =>
    loadOrder(STORAGE_KEY_FULL, FULL_WIDTH_WIDGETS)
  );
  const [gridOrder, setGridOrder] = useState<GridId[]>(() =>
    loadOrder(STORAGE_KEY_GRID, GRID_WIDGETS)
  );
  const [activeId, setActiveId] = useState<UniqueIdentifier | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleFullDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over || active.id === over.id) return;
    setFullOrder((prev) => {
      const oldIdx = prev.indexOf(active.id as FullWidthId);
      const newIdx = prev.indexOf(over.id as FullWidthId);
      const next = arrayMove(prev, oldIdx, newIdx);
      localStorage.setItem(STORAGE_KEY_FULL, JSON.stringify(next));
      return next;
    });
  }, []);

  const handleGridDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    setActiveId(null);
    if (!over || active.id === over.id) return;
    setGridOrder((prev) => {
      const oldIdx = prev.indexOf(active.id as GridId);
      const newIdx = prev.indexOf(over.id as GridId);
      const next = arrayMove(prev, oldIdx, newIdx);
      localStorage.setItem(STORAGE_KEY_GRID, JSON.stringify(next));
      return next;
    });
  }, []);

  if (loading) {
    // Section-shaped placeholders (no data is shown until it is real).
    return (
      <div className="p-4 md:p-8 space-y-6" aria-busy="true" aria-label="Loading your dashboard">
        <div className="rounded-2xl border border-border bg-card p-6 space-y-5">
          <div className="flex items-center gap-4">
            <Skeleton className="h-14 w-14 rounded-full" />
            <div className="space-y-2">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-4 w-56" />
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
          </div>
        </div>
        <Skeleton className="h-40 rounded-2xl" />
        <div className="grid md:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-44 rounded-2xl" />)}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-12 text-center max-w-lg mx-auto">
        <h2 className="text-2xl font-bold mb-2">Dashboard Unavailable</h2>
        <p className="text-muted-foreground mb-6">We couldn't load your dashboard data at this moment.</p>
        <Button onClick={() => refetchDashboard()}>Retry</Button>
      </div>
    );
  }

  // Journey progress / active course come from the dashboard response itself
  // (same overview computation) - no separate analytics request.
  const analytics = { journey_progress: data.stats.progress, active_course: data.activeCourse };

  // Server-enforced package lock:
  // Authentication != Subscription. Users without an active package see the
  // clear CTA, verification pending state, or renewal option.
  if (!data.package?.hasActivePackage) {
    const isPending = data.package.latestPayment?.status === "PENDING";
    const isRejected = data.package.latestPayment?.status === "REJECTED";
    const isExpired = data.package.status === "EXPIRED" || (data.package.status === "ACTIVE" && data.package.remainingDays === 0);

    return (
      <div className="min-h-[70vh] flex items-center justify-center p-6 bg-muted/30">
        <div className="max-w-md w-full bg-card border border-border rounded-[24px] shadow-sm p-10 relative overflow-hidden">
          {/* Decorative background elements */}
          <div className="absolute -top-10 -right-10 w-40 h-40 bg-[#D4A72C]/10 rounded-full blur-3xl pointer-events-none"></div>
          
          <div className="relative z-10 flex flex-col items-center text-center">
            {isPending ? (
              <>
                <div className="w-20 h-20 rounded-full bg-yellow-50 dark:bg-yellow-900/20 flex items-center justify-center mb-6 shadow-sm border border-yellow-100 dark:border-yellow-900/30">
                  <Clock className="w-10 h-10 text-yellow-500 animate-pulse" />
                </div>
                <h2 className="text-2xl font-bold text-primary dark:text-foreground mb-3">Verification Pending</h2>
                <p className="text-muted-foreground mb-6">
                  We are currently verifying your payment for the <span className="font-semibold text-foreground">{data.package.latestPayment?.planName}</span> package. This usually takes less than 30 minutes during working hours.
                </p>
                <div className="bg-muted w-full p-4 rounded-xl border border-border text-sm mb-6 text-left">
                  <div className="flex justify-between mb-2">
                    <span className="text-muted-foreground">Amount:</span>
                    <span className="font-medium text-foreground">Rs. {data.package.latestPayment?.amount}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Submitted:</span>
                    <span className="font-medium text-foreground">
                      {data.package.latestPayment?.submittedAt 
                        ? new Date(data.package.latestPayment.submittedAt).toLocaleDateString() 
                        : 'Recently'}
                    </span>
                  </div>
                </div>
                <Button variant="outline" className="w-full h-12 rounded-xl" onClick={() => window.location.reload()}>
                  Refresh Status
                </Button>
              </>
            ) : isRejected ? (
              <>
                <div className="w-20 h-20 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center mb-6 shadow-sm border border-red-100 dark:border-red-900/30">
                  <AlertCircle className="w-10 h-10 text-red-500" />
                </div>
                <h2 className="text-2xl font-bold text-primary dark:text-foreground mb-3">Payment Rejected</h2>
                <p className="text-muted-foreground mb-4">
                  Unfortunately, we couldn't verify your payment for the <span className="font-semibold text-foreground">{data.package.latestPayment?.planName}</span> package.
                </p>
                {data.package.latestPayment?.rejectionReason && (
                  <div className="bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-300 p-4 rounded-xl border border-red-100 dark:border-red-900/50 text-sm mb-6 w-full text-left">
                    <span className="font-semibold block mb-1">Reason:</span>
                    {data.package.latestPayment.rejectionReason}
                  </div>
                )}
                <Button
                  onClick={() => (window.location.href = "/student/plans")}
                  className="w-full bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-bold py-6 rounded-xl"
                >
                  Submit Payment Again
                </Button>
              </>
            ) : isExpired ? (
              <>
                <div className="w-20 h-20 rounded-full bg-orange-50 dark:bg-orange-900/20 flex items-center justify-center mb-6 shadow-sm border border-orange-100 dark:border-orange-900/30">
                  <Clock className="w-10 h-10 text-orange-500" />
                </div>
                <h2 className="text-2xl font-bold text-primary dark:text-foreground mb-3">Package Expired</h2>
                <p className="text-muted-foreground mb-8">
                  Your <span className="font-semibold text-foreground">{data.package.planName}</span> package has expired. Renew your package to restore access to all premium features.
                </p>
                <Button
                  onClick={() => (window.location.href = "/student/plans")}
                  className="w-full bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-bold py-6 rounded-xl"
                >
                  Renew Package
                </Button>
              </>
            ) : (
              <>
                <div className="w-20 h-20 rounded-full bg-[#D4A72C]/10 flex items-center justify-center mb-6 shadow-sm border border-[#D4A72C]/20">
                  <Lock className="w-10 h-10 text-[#D4A72C]" />
                </div>
                <h2 className="text-2xl font-bold text-primary dark:text-foreground mb-3">Welcome to LoksewaAI</h2>
                <p className="text-muted-foreground mb-8">
                  Your account is ready. Choose a premium package to unlock your full learning experience, including AI tutoring, mock exams, and analytics.
                </p>
                <Button
                  onClick={() => (window.location.href = "/student/plans")}
                  className="w-full bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] font-bold py-6 rounded-xl"
                >
                  Browse Premium Packages
                </Button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Recharts data
  const chartData = [...data.recentExams].reverse().map((exam, i) => ({
    name: `Ex ${i+1}`,
    score: exam.percentage,
    fullTitle: exam.title
  }));

  const WIDGET_LABELS: Record<string, string> = {
    motivation: "Quote of the Day",
    "quick-actions": "Quick Actions",
    "continue-study": "Continue Studying",
    "referral-card": "Invite & Earn",
    "referrals-list": "Recent Referrals",
    "your-progress": "Your Progress",
    "upcoming-exams": "Upcoming Exams",
  };

  return (
    <div className="p-4 md:p-8 max-w-[1400px] mx-auto space-y-8 bg-muted/50 min-h-[calc(100vh-72px)]">
      
      {/* 1. HEADER (not draggable — always pinned at top) */}
      <section className="bg-card p-6 md:p-8 rounded-[16px] border border-border shadow-sm flex flex-col xl:flex-row justify-between gap-8 relative">
        {/* Returning to this page within the 45s staleTime shows this cached
            data immediately (no skeleton) while a background refresh runs -
            this is the only visible trace of that refresh. */}
        {dashboardFetching && !loading && (
          <div className="absolute top-3 right-3 flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground bg-muted px-2.5 py-1 rounded-full">
            <div className="w-2.5 h-2.5 border-2 border-current border-t-transparent rounded-full animate-spin" /> Updating...
          </div>
        )}

        {/* Left Side: Avatar & Gamification */}
        <div className="flex-1 flex flex-col justify-between gap-6">
          <div className="flex gap-4 items-center">
            {data.profile.avatar ? (
              <RetryImage src={data.profile.avatar} alt="Avatar" className="w-14 h-14 rounded-full object-cover border-2 border-border/50 shadow-sm" />
            ) : (
              <div className="w-14 h-14 rounded-full bg-blue-50 dark:bg-blue-950/30 text-blue-600 flex items-center justify-center text-xl font-bold shrink-0 border-2 border-border/50 shadow-sm">
                {data.profile.name.charAt(0)}
              </div>
            )}
              <div className="flex flex-col justify-center">
              <h1 className="text-lg font-bold text-primary dark:text-foreground tracking-tight leading-tight">
                {data.profile.name}
              </h1>
              <p className="text-[12px] font-medium text-muted-foreground mt-0.5 flex items-center gap-1.5">
                <span className="bg-muted/80 text-muted-foreground px-2 py-0.5 rounded flex items-center gap-1"><GraduationCap className="w-3 h-3"/> Student</span>
                <span className="w-1 h-1 rounded-full bg-secondary"></span>
                <span>Applied for: <span className="font-semibold text-primary dark:text-foreground">{data.profile.targetPosition && data.profile.targetPosition !== "Student" ? data.profile.targetPosition : "Section Officer"}</span></span>
              </p>
              {studentCtx?.activeCourse ? (
                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <span className="text-[11px] font-semibold text-muted-foreground">Active Course:</span>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[12px] font-bold bg-[#D4A72C]/15 text-[#D4A72C] border border-[#D4A72C]/30">
                    <BookOpen className="w-3.5 h-3.5" />
                    {studentCtx.activeCourse.title}
                  </span>
                  {studentCtx.activeCourse.level_name && (
                    <span className="text-[11px] text-muted-foreground bg-muted px-2 py-0.5 rounded font-medium">
                      {studentCtx.activeCourse.level_name}
                    </span>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-[12px] text-muted-foreground">No active course yet.</span>
                  <Link href="/courses" className="text-[12px] font-semibold text-[#D4A72C] hover:underline flex items-center gap-1">
                    Explore Courses <ArrowRight className="w-3 h-3" />
                  </Link>
                </div>
              )}
              {referralData && (
                <div className="mt-1.5 text-[10px] font-bold text-blue-600 bg-blue-50 dark:bg-blue-950/30 inline-flex px-2 py-0.5 rounded-md border border-blue-100 dark:border-blue-900/50 self-start">
                  Level {referralData.profile.level}
                </div>
              )}
            </div>
          </div>

          {/* Gamification Stats */}
          {referralData ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 mt-2">
              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1">
                   <Sparkles className="w-3.5 h-3.5 text-[#D4A72C] fill-[#D4A72C]" /> Total XP
                 </div>
                 <div className="text-xl md:text-2xl font-bold text-primary dark:text-foreground mt-auto">
                   {referralData.profile.xp.toLocaleString()} XP
                 </div>
                 <div className="text-[10px] text-muted-foreground font-medium">All time</div>
              </div>
              
              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col relative overflow-hidden">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1">
                   <Target className="w-3.5 h-3.5 text-blue-500" /> Current Level
                 </div>
                 <div className="text-xl md:text-2xl font-bold text-primary dark:text-foreground mt-auto">
                   Level {referralData.profile.level}
                 </div>
                 <div className="text-[10px] text-muted-foreground font-medium z-10">
                   {referralData.profile.xp.toLocaleString()} / {referralData.settings?.xp_per_level ? (referralData.profile.level * referralData.settings.xp_per_level).toLocaleString() : '---'} XP
                 </div>
                 {referralData.settings?.xp_per_level && (
                   <div 
                     className="absolute bottom-0 left-0 h-1 bg-blue-500/20" 
                     style={{ width: `${Math.min((referralData.profile.xp / (referralData.profile.level * referralData.settings.xp_per_level)) * 100, 100)}%` }}
                   />
                 )}
              </div>

              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1">
                   <Flame className="w-3.5 h-3.5 text-orange-500 fill-orange-500" /> Day Streak
                 </div>
                 <div className="text-xl md:text-2xl font-bold text-primary dark:text-foreground mt-auto">
                   {data.stats.studyStreak} Days
                 </div>
                 <div className="text-[10px] text-muted-foreground font-medium">Active streak</div>
              </div>

              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1">
                   <Coins className="w-3.5 h-3.5 text-yellow-500 fill-yellow-500" /> Coins
                 </div>
                 <div className="text-xl md:text-2xl font-bold text-primary dark:text-foreground mt-auto">
                   {referralData.profile.coins.toLocaleString()}
                 </div>
                 <div className="text-[10px] text-muted-foreground font-medium">Available balance</div>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4 mt-2">
              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1"><Sparkles className="w-3.5 h-3.5 text-[#D4A72C] fill-[#D4A72C]" /> Total XP</div>
                 <div className="text-xl md:text-2xl font-bold text-muted-foreground mt-auto">—</div>
                 <div className="text-[10px] text-muted-foreground font-medium">
                   {referralData === undefined ? "Loading..." : (
                     <>Unable to load{" "}
                       <button type="button" onClick={() => refetchReferral()} className="underline font-semibold text-foreground">Retry</button>
                     </>
                   )}
                 </div>
              </div>
              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1"><Target className="w-3.5 h-3.5 text-blue-500" /> Current Level</div>
                 <div className="text-xl md:text-2xl font-bold text-muted-foreground mt-auto">—</div>
              </div>
              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1"><Flame className="w-3.5 h-3.5 text-orange-500 fill-orange-500" /> Day Streak</div>
                 <div className="text-xl md:text-2xl font-bold text-primary dark:text-foreground mt-auto">{data.stats.studyStreak} Days</div>
                 <div className="text-[10px] text-muted-foreground font-medium">Active streak</div>
              </div>
              <div className="bg-muted border border-border/50 rounded-xl p-3 md:p-4 flex flex-col">
                 <div className="flex items-center gap-1.5 text-[10px] md:text-xs font-bold text-muted-foreground uppercase tracking-wider mb-1"><Coins className="w-3.5 h-3.5 text-yellow-500 fill-yellow-500" /> Coins</div>
                 <div className="text-xl md:text-2xl font-bold text-muted-foreground mt-auto">—</div>
              </div>
            </div>
          )}
        </div>

        {/* Right Side: Profile Completion and Subscription */}
        <div className="xl:w-[280px] shrink-0 self-start w-full flex flex-col gap-4">
          {data.profile.completionPercentage < 100 && (
            <div className="bg-yellow-50 dark:bg-yellow-950/30 border border-yellow-200 dark:border-yellow-900/50 p-4 rounded-xl">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-bold text-yellow-800 dark:text-yellow-200">Profile Completion</span>
                <span className="text-sm font-bold text-yellow-800 dark:text-yellow-200">{data.profile.completionPercentage}%</span>
              </div>
              <Progress value={data.profile.completionPercentage} className="h-1.5 bg-yellow-200 dark:bg-yellow-900/40" indicatorClassName="bg-yellow-500" />
              <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-2">Complete your profile to get better recommendations.</p>
              <Link href="/student/settings" className="text-xs font-bold text-yellow-800 dark:text-yellow-200 hover:underline mt-1 inline-block">Complete Profile &rarr;</Link>
            </div>
          )}

          <div className="bg-[#0B2545] dark:bg-[#0D1B2A] text-white p-5 rounded-2xl border border-[#163E6B] dark:border-[#243B53] shadow-lg relative overflow-hidden">
            <div className="absolute right-0 top-0 w-32 h-32 bg-white/5 rounded-full blur-2xl -mr-10 -mt-10 pointer-events-none"></div>

            {data.package?.hasActivePackage && data.package.planName ? (
              <div className="relative z-10 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-[#D4A72C] rounded-lg">
                      <Sparkles className="w-4 h-4 text-[#0A1118]" />
                    </div>
                    <span className="font-bold text-[15px] tracking-tight text-white">{data.package.planName}</span>
                  </div>
                  <span className="bg-emerald-500/20 text-emerald-400 text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase border border-emerald-500/30">
                    {data.package.status || "ACTIVE"}
                  </span>
                </div>

                {(studentCtx?.activeCourse?.title || data.activeCourse?.name) && (
                  <div className="font-semibold text-slate-200 text-xs leading-snug">
                    {studentCtx?.activeCourse?.title || data.activeCourse?.name}
                  </div>
                )}

                <div className="pt-2 border-t border-white/15 text-xs text-slate-300 space-y-1">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Remaining Access:</span>
                    <span className="font-bold text-[#D4A72C]">{data.package.remainingDays ?? 0} days</span>
                  </div>
                  {data.package.expiryDate && (
                    <div className="flex justify-between text-[11px] text-slate-400">
                      <span>Expires:</span>
                      <span className="font-medium text-slate-200">{new Date(data.package.expiryDate).toLocaleDateString()}</span>
                    </div>
                  )}
                </div>

                <Button asChild className="w-full mt-2 bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] h-9 text-xs font-bold shadow-sm transition-colors">
                  <Link href="/student/courses">Go to My Courses</Link>
                </Button>
              </div>
            ) : analytics?.active_course ? (
              <div className="relative z-10 space-y-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-[#D4A72C] rounded-lg"><Sparkles className="w-4 h-4 text-[#0A1118]" /></div>
                  <span className="font-bold text-lg tracking-tight text-white">Active Plan</span>
                </div>
                <div className="font-semibold text-white text-sm">{analytics.active_course.name}</div>
                <div className="pt-2 border-t border-white/15">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs text-slate-400 font-medium">Journey Progress</span>
                    <span className="text-xs font-bold text-[#D4A72C]">{analytics.journey_progress}%</span>
                  </div>
                  <Progress value={analytics.journey_progress} className="h-1.5 bg-white/10" indicatorClassName="bg-[#D4A72C]" />
                </div>
                <Button asChild className="w-full mt-2 bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] h-9 text-xs font-bold">
                  <Link href="/student/study-plan">Resume Journey</Link>
                </Button>
              </div>
            ) : (
              <div className="relative z-10 space-y-3">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-[#D4A72C]/20 rounded-lg"><Sparkles className="w-4 h-4 text-[#D4A72C]" /></div>
                  <span className="font-bold text-lg tracking-tight text-white">Unlock Full Access</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Get access to premium preparation tools, AI tutoring, and advanced mock exams.
                </p>
                <Button asChild className="w-full mt-2 bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-[#0A1118] h-9 text-xs font-bold">
                  <Link href="/student/plans">View Plans</Link>
                </Button>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Official Loksewa Exam Countdown & Upcoming Mock Exam Banner */}
      <section className="space-y-4">
        <LoksewaExamCountdown />
        <MockExamCountdown />
      </section>

      {/* ─── DRAGGABLE FULL-WIDTH SECTIONS ─────────────────────────────────────── */}
      <DndContext

        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={(e) => setActiveId(e.active.id)}
        onDragEnd={handleFullDragEnd}
      >
        <SortableContext items={fullOrder} strategy={verticalListSortingStrategy}>
          <div className="space-y-8">
            {fullOrder.map((widgetId) => {
              if (widgetId === "motivation" && motivation) {
                return (
                  <SortableWidget key={widgetId} id={widgetId}>
                    <section className="bg-gradient-to-r from-blue-50 dark:from-blue-950/40 to-indigo-50 dark:to-indigo-950/40 border border-blue-100 dark:border-blue-900/50 rounded-[16px] p-6 shadow-sm relative overflow-hidden group/widget">
                      <div data-focus-hide className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                        <Sparkles className="w-24 h-24 text-blue-600" />
                      </div>
                      <div className="flex items-start gap-4 relative z-10">
                        <div className="p-3 bg-card rounded-full shadow-sm">
                          <Flame className="w-6 h-6 text-orange-500 fill-orange-500" />
                        </div>
                        <div className="flex-1">
                          <h3 className="text-sm font-bold text-blue-900 dark:text-blue-200 uppercase tracking-wider mb-1">Quote of the Day</h3>
                          <p className="text-lg md:text-xl font-medium text-foreground italic">"{motivation.message}"</p>
                        </div>
                      </div>
                    </section>
                  </SortableWidget>

                );
              }

              if (widgetId === "quick-actions") {
                return (
                  <SortableWidget key={widgetId} id={widgetId}>
                    <div className="relative group/widget">
                      <section className="grid grid-cols-2 md:grid-cols-6 gap-3">
                        {QUICK_ACTIONS.map((action, i) => (
                          <Link key={i} href={action.href} className="flex flex-col items-center justify-center p-4 bg-card rounded-xl border hover:border-[#D4A72C] hover:shadow-md transition-all group text-center gap-2">
                            <div className="p-3 rounded-full bg-muted group-hover:bg-[#D4A72C]/10 transition-colors">
                              {action.icon === 'target' && <Target className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                              {action.icon === 'file-text' && <FileText className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                              {action.icon === 'book-open' && <BookOpen className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                              {action.icon === 'message-square' && <MessageSquare className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                              {action.icon === 'calendar' && <Calendar className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                              {action.icon === 'shopping-bag' && <ShoppingBag className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                              {action.icon === 'check-circle' && <CheckCircle2 className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                              {action.icon === 'gift' && <Gift className="w-5 h-5 text-blue-600 group-hover:text-[#D4A72C]" />}
                            </div>
                            <span className="text-[13px] font-semibold text-foreground flex items-center gap-1.5">
                              {action.label}
                              {action.label === 'Invite Friends' && (
                                <span data-focus-hide className="bg-red-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider">New</span>
                              )}
                            </span>
                          </Link>
                        ))}
                      </section>
                    </div>
                  </SortableWidget>
                );
              }

              if (widgetId === "continue-study" && data.continueLearning) {
                return (
                  <SortableWidget key={widgetId} id={widgetId}>
                    <section className="relative overflow-hidden bg-gradient-to-r from-[#0B2545] via-[#0E3259] to-[#163E6B] text-white rounded-[16px] shadow-lg border border-[#163E6B] group/widget">
                      <div className="absolute right-0 top-0 w-64 h-full bg-gradient-to-l from-[#163E6B]/50 to-transparent pointer-events-none"></div>
                      <div className="absolute -right-10 -top-10 w-40 h-40 rounded-full bg-[#D4A72C] opacity-10 blur-[60px] pointer-events-none"></div>
                      <div className="relative p-6 md:p-8 flex flex-col md:flex-row md:items-center justify-between gap-6 z-10">
                        <div className="flex items-start gap-5">
                          <div className="bg-[#0B2545] border border-[#163E6B] p-3.5 rounded-[12px] hidden sm:flex shrink-0">
                            <BookOpen className="h-7 w-7 text-[#D4A72C]" strokeWidth={1.5} />
                          </div>
                          <div>
                            <div className="text-[12px] font-bold text-[#D4A72C] uppercase tracking-widest mb-1">
                              Unfinished {data.continueLearning.type === 'practice' ? 'Practice' : 'Exam'}
                            </div>
                            <h3 className="font-bold text-[20px] text-white tracking-tight">{data.continueLearning.title}</h3>
                            <div className="flex items-center gap-4 mt-5">
                              <Progress value={data.continueLearning.progress} className="w-48 h-1.5 bg-card/20" indicatorClassName="bg-[#D4A72C]" />
                              <span className="text-[13px] font-bold text-white">{data.continueLearning.progress}%</span>
                            </div>
                          </div>
                        </div>
                        <Button className="bg-[#D4A72C] hover:bg-[#b08b25] text-slate-950 font-bold px-8 h-12 rounded-xl shrink-0 shadow-md transition-all hover:scale-[1.02]" asChild>
                          <Link href={data.continueLearning.url}>
                            Resume <ArrowRight className="ml-2 h-5 w-5" />
                          </Link>
                        </Button>
                      </div>
                    </section>
                  </SortableWidget>
                );
              }

              if (widgetId === "referral-card" && referralData && referralData.settings?.is_enabled) {
                return (
                  <SortableWidget key={widgetId} id={widgetId}>
                    <section data-focus-hide className="bg-gradient-to-r from-[#0B2545] to-[#163E6B] rounded-[16px] shadow-lg border border-[#163E6B] overflow-hidden text-white group/widget">
                      <div className="p-6 md:p-8 flex flex-col md:flex-row items-center justify-between gap-8 relative z-10">
                        <div className="flex-1 space-y-3">
                          <div className="flex items-center gap-2">
                            <Gift className="w-6 h-6 text-[#D4A72C]" />
                            <h2 className="text-xl md:text-2xl font-bold tracking-tight">Invite Friends & Earn</h2>
                          </div>
                          <p className="text-slate-300 text-sm">
                            Earn <span className="font-bold text-[#D4A72C]">{referralData.settings.referrer_xp_reward} XP</span> for every friend who joins LoksewaAI and completes registration. 
                          </p>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6 pt-4 border-t border-white/10">
                            <div>
                              <div className="text-muted-foreground text-xs font-medium uppercase mb-1">Referrals</div>
                              <div className="flex items-center gap-2"><Users className="w-4 h-4 text-blue-400" /><span className="font-bold">{referralData.stats.successful_referrals}</span></div>
                            </div>
                            <div>
                              <div className="text-muted-foreground text-xs font-medium uppercase mb-1">Pending</div>
                              <div className="flex items-center gap-2"><Clock className="w-4 h-4 text-orange-400" /><span className="font-bold">{referralData.stats.pending_referrals}</span></div>
                            </div>
                            <div>
                              <div className="text-muted-foreground text-xs font-medium uppercase mb-1">XP Earned</div>
                              <div className="flex items-center gap-2"><TrendingUp className="w-4 h-4 text-purple-400" /><span className="font-bold">{referralData.stats.total_xp_earned}</span></div>
                            </div>
                            <div>
                              <div className="text-muted-foreground text-xs font-medium uppercase mb-1">Coins</div>
                              <div className="flex items-center gap-2"><Coins className="w-4 h-4 text-yellow-400" /><span className="font-bold">{referralData.stats.total_coins_earned}</span></div>
                            </div>
                          </div>
                          <div className="mt-6 pt-4 border-t border-white/10 hidden md:block">
                            <div className="flex justify-between items-center mb-2">
                              <span className="text-xs text-slate-300">Next Reward: <strong className="text-white">10 Referrals</strong></span>
                              <span className="text-xs text-slate-300 font-bold">{referralData.stats.successful_referrals} / 10</span>
                            </div>
                            <Progress value={Math.min((referralData.stats.successful_referrals / 10) * 100, 100)} className="h-2 bg-card/10" indicatorClassName="bg-[#4ade80]" />
                            <p className="text-[10px] text-muted-foreground mt-2">
                              {Math.max(10 - referralData.stats.successful_referrals, 0)} more referrals to unlock: <strong className="text-[#D4A72C]">Referral Champion (+500 XP)</strong>
                            </p>
                          </div>
                        </div>
                        <div className="w-full md:w-auto shrink-0 flex flex-col gap-4">
                          <div className="bg-black/20 p-5 rounded-xl border border-white/10">
                            <div className="text-xs text-slate-300 font-medium uppercase tracking-wider mb-2 text-center">Your Referral Code</div>
                            <div className="font-mono text-xl font-bold tracking-widest text-[#4ade80] text-center mb-4">
                              {referralData.profile.referral_code}
                            </div>
                            <div className="flex flex-col sm:flex-row gap-2">
                              <Button variant="secondary" className="bg-card/10 hover:bg-card/20 text-white border-0 flex-1 h-9 px-2"
                                onClick={() => {
                                  const link = `${typeof window !== 'undefined' ? window.location.origin : ''}/signup?ref=${referralData.profile.referral_code}`;
                                  navigator.clipboard.writeText(link);
                                  alert("Referral link copied!");
                                }} title="Copy Link">
                                <Copy className="w-4 h-4 mr-1" /> Copy
                              </Button>
                              <Button variant="secondary" className="bg-[#1DA1F2]/20 hover:bg-[#1DA1F2]/40 text-[#1DA1F2] border-0 h-9 px-3"
                                onClick={() => {
                                  const link = `${typeof window !== 'undefined' ? window.location.origin : ''}/signup?ref=${referralData.profile.referral_code}`;
                                  if (navigator.share) {
                                    navigator.share({ title: 'Join me on LoksewaAI', text: 'Join me on LoksewaAI and start your Loksewa preparation. Use my referral link to get started!', url: link }).catch(console.error);
                                  } else {
                                    window.open(`https://twitter.com/intent/tweet?url=${encodeURIComponent(link)}&text=Join me on LoksewaAI!`);
                                  }
                                }} title="Share">
                                <Share2 className="w-4 h-4" />
                              </Button>
                              <Button className="bg-[#D4A72C] hover:bg-[#D4A72C]/90 text-white flex-1 h-9 px-2" asChild>
                                <Link href="/student/referrals">Details <ArrowRight className="w-4 h-4 ml-1" /></Link>
                              </Button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </section>
                  </SortableWidget>
                );
              }

              return null;
            })}
          </div>
        </SortableContext>

        <DragOverlay>
          {activeId && FULL_WIDTH_WIDGETS.includes(activeId as FullWidthId) ? (
            <WidgetDragGhost label={WIDGET_LABELS[activeId as string] ?? String(activeId)} />
          ) : null}
        </DragOverlay>
      </DndContext>

      {/* ─── DRAGGABLE GRID SECTIONS ────────────────────────────────────────────── */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={(e) => setActiveId(e.active.id)}
        onDragEnd={handleGridDragEnd}
      >
        <SortableContext items={gridOrder} strategy={verticalListSortingStrategy}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
            {gridOrder.map((widgetId) => {
              if (widgetId === "referrals-list") {
                return (
                  <SortableWidget key={widgetId} id={widgetId}>
                    <div className="bg-card border border-border shadow-sm rounded-[16px] flex flex-col overflow-hidden group/widget">
                      <div className="p-4 border-b border-border/50 bg-muted/50 flex justify-between items-center">
                        <h3 className="text-base font-bold text-primary dark:text-foreground flex items-center gap-2">
                          <Users className="w-4 h-4 text-blue-500" /> Recent Referrals
                        </h3>
                        <div className="flex items-center gap-1">

                          <Button variant="ghost" size="sm" className="text-xs text-blue-600 h-8 font-semibold" asChild>
                            <Link href="/student/referrals">View all</Link>
                          </Button>
                        </div>
                      </div>
                      <div className="p-0 flex-1 flex flex-col">
                        {referralHistory.length > 0 ? (
                          <div className="divide-y divide-slate-100">
                            {referralHistory.slice(0, 4).map((item, i) => (
                              <div key={i} className="flex justify-between items-center p-4 hover:bg-muted transition-colors">
                                <span className="text-sm font-semibold text-primary dark:text-foreground">{item.referred_username}</span>
                                <div className="flex items-center gap-3">
                                  <span className={cn("text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider", 
                                    item.status === 'rewarded' ? 'bg-green-100 text-green-700 dark:text-green-300' : 
                                    item.status === 'qualified' ? 'bg-blue-100 text-blue-700' : 
                                    'bg-orange-100 text-orange-700 dark:text-orange-300')}>
                                    {item.status}
                                  </span>
                                  <span className="text-xs font-bold text-[#D4A72C] w-14 text-right">
                                    {item.reward_amount > 0 ? `+${item.reward_amount} XP` : '—'}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="p-8 text-center flex flex-col items-center justify-center h-full text-muted-foreground">
                            <Users className="w-10 h-10 text-slate-200 mb-3" />
                            <p className="text-sm font-medium text-primary dark:text-foreground">No referrals yet</p>
                            <p className="text-xs mt-1">Share your code to start earning!</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </SortableWidget>
                );
              }

              if (widgetId === "your-progress") {
                return (
                  <SortableWidget key={widgetId} id={widgetId}>
                    <div className="bg-card border border-border shadow-sm rounded-[16px] flex flex-col overflow-hidden group/widget">
                      <div className="p-4 border-b border-border/50 bg-muted/50 flex justify-between items-center">
                        <h3 className="text-base font-bold text-primary dark:text-foreground flex items-center gap-2">
                          <TrendingUp className="w-4 h-4 text-purple-500" /> Your Progress
                        </h3>
                        <div className="flex items-center gap-2">

                          <div className="text-[11px] font-bold text-muted-foreground flex items-center cursor-pointer hover:text-primary dark:text-foreground uppercase tracking-wider">
                            This Week <ChevronRight className="w-3 h-3 ml-0.5 rotate-90" />
                          </div>
                        </div>
                      </div>
                      <div className="p-6 flex-1 flex flex-col justify-center gap-6">
                        <div>
                          <div className="flex justify-between items-end mb-2">
                            <span className="text-sm font-semibold text-muted-foreground">Practice Score</span>
                            <span className="text-sm font-bold text-primary dark:text-foreground">{data.stats.averageScore}%</span>
                          </div>
                          <Progress value={data.stats.averageScore} className="h-2 bg-muted/80" indicatorClassName="bg-blue-500" />
                        </div>
                        <div>
                          <div className="flex justify-between items-end mb-2">
                            <span className="text-sm font-semibold text-muted-foreground">Mock Exams</span>
                            <span className="text-sm font-bold text-primary dark:text-foreground">{data.stats.completedExams} / {Math.max(data.stats.completedExams, data.stats.totalExams)}</span>
                          </div>
                          <Progress value={data.stats.totalExams > 0 ? Math.min((data.stats.completedExams / data.stats.totalExams) * 100, 100) : 0} className="h-2 bg-muted/80" indicatorClassName="bg-purple-500" />
                        </div>
                        <div>
                          <div className="flex justify-between items-end mb-2">
                            <span className="text-sm font-semibold text-muted-foreground">Questions Solved</span>
                            <span className="text-sm font-bold text-primary dark:text-foreground">{data.stats.questionsAttempted}</span>
                          </div>
                          <Progress value={Math.min((data.stats.questionsAttempted / Math.max(data.stats.questionsAttempted + 50, 100)) * 100, 100)} className="h-2 bg-muted/80" indicatorClassName="bg-[#D4A72C]" />
                        </div>
                        <div>
                          <div className="flex justify-between items-end mb-2">
                            <span className="text-sm font-semibold text-muted-foreground">Accuracy</span>
                            <span className="text-sm font-bold text-primary dark:text-foreground">{data.stats.accuracy}%</span>
                          </div>
                          <Progress value={data.stats.accuracy} className="h-2 bg-muted/80" indicatorClassName="bg-green-500" />
                        </div>
                      </div>
                    </div>
                  </SortableWidget>
                );
              }

              if (widgetId === "upcoming-exams") {
                return (
                  <SortableWidget key={widgetId} id={widgetId}>
                    <div className="bg-card border border-border shadow-sm rounded-[16px] flex flex-col overflow-hidden group/widget">
                      <div className="p-4 border-b border-border/50 bg-muted/50 flex justify-between items-center">
                        <h3 className="text-base font-bold text-primary dark:text-foreground flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-orange-500" /> Upcoming
                        </h3>
                        <div className="flex items-center gap-1">

                          <Button variant="ghost" size="sm" className="text-xs text-blue-600 h-8 font-semibold" asChild>
                            <Link href="/student/exams">View all</Link>
                          </Button>
                        </div>
                      </div>
                      <div className="p-0 flex-1 flex flex-col">
                        {data.todaysPlan.filter(p => p.type === 'exam').length > 0 ? (
                          <div className="divide-y divide-slate-100">
                            {data.todaysPlan.filter(p => p.type === 'exam').map(exam => (
                              <div key={exam.id} className="p-5 hover:bg-muted transition-colors">
                                <div className="flex gap-4">
                                  <div className="mt-1"><Calendar className="w-5 h-5 text-blue-500" /></div>
                                  <div className="flex-1">
                                    <h4 className="text-sm font-bold text-primary dark:text-foreground leading-tight mb-1">{exam.title}</h4>
                                    <p className="text-xs text-muted-foreground font-medium">Today • {exam.duration} mins</p>
                                    <Button size="sm" variant="outline" className="w-full mt-4 text-xs font-bold border-blue-200 text-blue-700 hover:bg-blue-50 dark:bg-blue-950/30 hover:text-blue-800">
                                      Start Now
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="p-8 text-center flex flex-col items-center justify-center h-full text-muted-foreground">
                            <Calendar className="w-10 h-10 text-slate-200 mb-3" />
                            <p className="text-sm font-medium text-primary dark:text-foreground">No upcoming exams</p>
                            <p className="text-xs mt-1">Check back later or view past results.</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </SortableWidget>
                );
              }

              return null;
            })}
          </div>
        </SortableContext>

        <DragOverlay>
          {activeId && GRID_WIDGETS.includes(activeId as GridId) ? (
            <WidgetDragGhost label={WIDGET_LABELS[activeId as string] ?? String(activeId)} />
          ) : null}
        </DragOverlay>
      </DndContext>

    </div>
  );
}
