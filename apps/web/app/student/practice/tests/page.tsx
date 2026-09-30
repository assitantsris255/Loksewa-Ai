"use client";

import { AlertCircle, ArrowRight, ClipboardList, Clock, Loader2, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useOptionalStudentContext } from "@/contexts/StudentContext";
import { studentExamsApi } from "@/lib/api/student-exams";

export default function TopicwiseTestsPage() {
  const studentCtx = useOptionalStudentContext();
  const courseId = studentCtx?.activeCourse?.id;
  const contextLoading = studentCtx?.isLoading ?? false;
  const testsQuery = useQuery({
    queryKey: ["topicwise-tests", courseId ?? null],
    queryFn: () => studentExamsApi.getTopicwiseTests(courseId),
    enabled: !contextLoading,
    staleTime: 60_000,
  });
  const tests = testsQuery.data ?? [];

  return (
    <main className="mx-auto max-w-[1000px] space-y-7 px-4 py-8 md:px-8">
      <header className="border-b border-border pb-5">
        <Link href="/student/practice" className="text-sm font-semibold text-muted-foreground hover:text-primary">Practice</Link>
        <div className="mt-3 flex items-center gap-3">
          <ClipboardList className="h-6 w-6 text-sky-700" aria-hidden="true" />
          <h1 className="text-2xl font-bold text-primary dark:text-foreground">Topicwise Test</h1>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">Published tests created by your instructors.</p>
      </header>

      {contextLoading || (testsQuery.isLoading && !testsQuery.data) ? (
        <div className="space-y-3" aria-busy="true">
          <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading available tests...</p>
          {[0, 1, 2].map((item) => <div key={item} className="h-24 animate-pulse border border-border bg-muted/40" />)}
        </div>
      ) : testsQuery.isError ? (
        <div className="flex items-center gap-3 border-y border-red-200 py-5 text-sm text-red-700 dark:border-red-900 dark:text-red-300" role="alert">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span className="flex-1">Available tests could not be loaded.</span>
          <Button variant="outline" size="sm" onClick={() => testsQuery.refetch()}><RotateCcw className="mr-2 h-4 w-4" />Retry</Button>
        </div>
      ) : tests.length === 0 ? (
        <section className="border-y border-border py-10 text-center">
          <p className="font-semibold text-primary dark:text-foreground">No topicwise tests available.</p>
          <p className="mt-1 text-sm text-muted-foreground">Published tests for your active course will appear here.</p>
        </section>
      ) : (
        <div className="divide-y divide-border border-y border-border">
          {tests.map((test) => (
            <article key={test.id} className="flex flex-wrap items-center gap-4 py-5">
              <div className="min-w-0 flex-1">
                <h2 className="font-semibold text-primary dark:text-foreground">{test.title}</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {[test.course_title, test.topic_name, test.subject_name].filter(Boolean).join(" · ")}
                </p>
                {test.description && <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{test.description}</p>}
                <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium text-muted-foreground">
                  <span>{test.total_questions} questions</span>
                  <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{test.time_limit} min</span>
                </div>
              </div>
              <Button asChild variant="outline" className="shrink-0">
                <Link href={`/student/exams/${test.id}`}>
                  View Test <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}