"use client";

import { AlertCircle, ArrowRight, BookOpen, Bookmark, ClipboardList, Loader2, RefreshCw, Target, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useRevisionSummary } from "@/lib/practice-hooks";

export default function PracticeSetupPage() {
  const router = useRouter();
  const summaryQuery = useRevisionSummary();
  const summary = summaryQuery.data;

  const quickStarts = [
    {
      id: "random",
      label: "Random",
      description: "Practice approved questions from your authorized Question Bank.",
      count: null,
      icon: Zap,
      href: "/student/practice/session?quick=random&q=20",
      tone: "text-sky-700 bg-sky-100 dark:text-sky-300 dark:bg-sky-950/50",
    },
    {
      id: "weak",
      label: "Weak Topic",
      description: "Work on topics where your real answer history shows room to improve.",
      count: summary?.weak_topics ?? null,
      icon: Target,
      href: "/student/practice/revision?focus=weak_topics",
      tone: "text-rose-700 bg-rose-100 dark:text-rose-300 dark:bg-rose-950/50",
    },
    {
      id: "saved",
      label: "Saved Questions",
      description: "Practice questions you have bookmarked while studying or taking exams.",
      count: null,
      icon: Bookmark,
      href: "/student/practice/saved",
      tone: "text-amber-700 bg-amber-100 dark:text-amber-300 dark:bg-amber-950/50",
    },
    {
      id: "incorrect",
      label: "Recently Incorrect",
      description: "Revisit approved questions from your recent incorrect answers.",
      count: summary?.recent_mistakes ?? null,
      icon: RefreshCw,
      href: "/student/practice/revision?focus=recent_mistakes",
      tone: "text-teal-700 bg-teal-100 dark:text-teal-300 dark:bg-teal-950/50",
    },
  ];

  return (
    <main className="mx-auto max-w-[1050px] space-y-12 px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-border pb-6">
        <p className="text-xs font-bold uppercase text-muted-foreground">Student Portal</p>
        <h1 className="mt-2 text-3xl font-bold text-primary dark:text-foreground">Practice</h1>
      </header>

      <section aria-labelledby="quick-start-heading">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 id="quick-start-heading" className="text-xl font-bold text-primary dark:text-foreground">Quick Start</h2>
            <p className="mt-1 text-sm text-muted-foreground">Practice instantly based on what you want to work on.</p>
          </div>
          {summaryQuery.isLoading && <span className="flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading practice options...</span>}
        </div>

        {summaryQuery.isError && (
          <div className="mb-3 flex items-center gap-3 border-y border-red-200 py-3 text-sm text-red-700 dark:border-red-900 dark:text-red-300" role="alert">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="flex-1">Could not load your performance counts.</span>
            <Button type="button" variant="outline" size="sm" onClick={() => summaryQuery.refetch()}>Retry</Button>
          </div>
        )}

        <div className="divide-y divide-border border-y border-border">
          {quickStarts.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => router.push(item.href)}
              className="group flex w-full items-center gap-4 py-5 text-left transition-colors hover:bg-muted/40"
            >
              <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[8px] ${item.tone}`}>
                <item.icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold text-primary dark:text-foreground">{item.label}</span>
                <span className="mt-0.5 block text-sm text-muted-foreground">{item.description}</span>
              </span>
              {item.count !== null && (
                <span className="min-w-8 text-right text-sm font-semibold tabular-nums text-muted-foreground">
                  {item.count}
                </span>
              )}
              <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1" aria-hidden="true" />
            </button>
          ))}
        </div>
      </section>

      <section aria-labelledby="topicwise-heading">
        <div className="mb-5 border-b border-border pb-4">
          <h2 id="topicwise-heading" className="text-xl font-bold text-primary dark:text-foreground">Topicwise Practice</h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Link href="/student/practice/study" className="group flex min-h-32 items-center gap-4 border border-border p-5 transition-colors hover:bg-muted/40">
            <BookOpen className="h-6 w-6 shrink-0 text-amber-600" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block font-semibold text-primary dark:text-foreground">Topicwise Study</span>
              <span className="mt-1 block text-sm text-muted-foreground">Learn at your own pace. No timer, no fixed count, answers available while studying.</span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </Link>
          <Link href="/student/practice/tests" className="group flex min-h-32 items-center gap-4 border border-border p-5 transition-colors hover:bg-muted/40">
            <ClipboardList className="h-6 w-6 shrink-0 text-sky-700" aria-hidden="true" />
            <span className="min-w-0 flex-1">
              <span className="block font-semibold text-primary dark:text-foreground">Topicwise Test</span>
              <span className="mt-1 block text-sm text-muted-foreground">Take an admin-created test with a fixed question set and strict timer.</span>
            </span>
            <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-1" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </main>
  );
}