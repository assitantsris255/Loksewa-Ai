"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowDown, ArrowLeft, ArrowUp, Bookmark, ListOrdered } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useOptionalStudentContext } from "@/contexts/StudentContext";
import { practiceApi, SavedQuestion, StudyPage } from "@/lib/api/practice";
import { practiceError, practiceErrorMessage, PracticeError } from "@/lib/practice-errors";
import { useSavedQuestions, practiceResultKey } from "@/lib/practice-hooks";
import { QuestionSkeleton, TopicPracticeBrowser } from "@/components/practice/TopicPracticeBrowser";

export default function SavedQuestionsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const studentCtx = useOptionalStudentContext();
  const courseId = studentCtx?.activeCourse?.id ?? null;
  const {
    savedIds,
    savedQuestions,
    toggle,
    isError: savedError,
    refetch: refetchSaved,
  } = useSavedQuestions();
  const [session, setSession] = useState<StudyPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [error, setError] = useState<PracticeError | null>(null);
  const [orderDraft, setOrderDraft] = useState<SavedQuestion[] | null>(null);
  const [savingOrder, setSavingOrder] = useState(false);
  const [orderError, setOrderError] = useState<string | null>(null);

  const start = async () => {
    setLoading(true);
    setError(null);
    setEmpty(false);
    try {
      setSession(await practiceApi.startSavedSession(courseId));
    } catch (cause) {
      const nextError = practiceError(cause, "start");
      if (nextError.kind === "no-questions") setEmpty(true);
      else setError(nextError);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (studentCtx?.isLoading) return;
    setSession(null);
    void start();
    // Start a new course-scoped saved session after an active-course change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, studentCtx?.isLoading]);

  const title = (
    <div className="flex items-center gap-3">
      <Bookmark className="h-6 w-6 text-amber-600" aria-hidden="true" />
      <div>
        <h1 className="text-2xl font-bold text-primary dark:text-foreground">Saved Questions</h1>
        <p className="mt-1 text-sm text-muted-foreground">Practice your saved questions from this course.</p>
      </div>
    </div>
  );

  const orderedBookmarks = orderDraft ?? savedQuestions;
  const hasCustomOrder = savedQuestions.some((bookmark) => bookmark.custom_order !== null);
  const orderChanged = !!orderDraft && orderDraft.some((bookmark, index) => bookmark.id !== savedQuestions[index]?.id);

  const moveBookmark = (index: number, offset: number) => {
    if (!orderDraft) return;
    const target = index + offset;
    if (target < 0 || target >= orderDraft.length) return;
    const next = [...orderDraft];
    [next[index], next[target]] = [next[target]!, next[index]!];
    setOrderDraft(next);
  };

  const saveOrder = async () => {
    if (!orderDraft || !orderChanged) return;
    setSavingOrder(true);
    setOrderError(null);
    try {
      await practiceApi.orderSavedQuestions(orderDraft.map((bookmark) => bookmark.id), courseId);
      setOrderDraft(null);
      await refetchSaved();
    } catch (cause) {
      setOrderError(practiceErrorMessage(cause, "save"));
    } finally {
      setSavingOrder(false);
    }
  };

  const resetOrder = async () => {
    setSavingOrder(true);
    setOrderError(null);
    try {
      await practiceApi.resetSavedQuestionOrder(courseId);
      setOrderDraft(null);
      await refetchSaved();
    } catch (cause) {
      setOrderError(practiceErrorMessage(cause, "save"));
    } finally {
      setSavingOrder(false);
    }
  };

  if (loading && !session) {
    return <main className="mx-auto max-w-[900px] space-y-6 px-4 py-8 md:px-8" aria-busy="true">{title}<QuestionSkeleton count={3} /></main>;
  }

  if (empty && !session) {
    return (
      <main className="mx-auto max-w-[760px] space-y-6 px-4 py-8 md:px-8">
        <Button variant="ghost" size="sm" onClick={() => router.push("/student/practice")}><ArrowLeft className="mr-2 h-4 w-4" />Practice</Button>
        {title}
        <section className="border-y border-border py-10 text-center">
          <p className="font-semibold text-primary dark:text-foreground">No saved questions yet.</p>
          <p className="mt-1 text-sm text-muted-foreground">Save questions while studying to find them here.</p>
        </section>
      </main>
    );
  }

  if (error && !session) {
    return (
      <main className="mx-auto max-w-[760px] space-y-6 px-4 py-8 md:px-8">
        <Button variant="ghost" size="sm" onClick={() => router.push("/student/practice")}><ArrowLeft className="mr-2 h-4 w-4" />Practice</Button>
        {title}
        <div className="flex items-center gap-3 border-y border-red-200 py-5 text-sm text-red-700 dark:border-red-900 dark:text-red-300" role="alert">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span className="flex-1">{error.message}</span>
          {error.retryable && <Button variant="outline" size="sm" onClick={() => void start()}>Retry</Button>}
        </div>
      </main>
    );
  }

  if (!session) return null;

  return (
    <main className="mx-auto max-w-[1000px] space-y-6 px-4 py-8 md:px-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        {title}
        <Button variant="ghost" size="sm" onClick={() => router.push("/student/practice")}><ArrowLeft className="mr-2 h-4 w-4" />Practice</Button>
      </div>
      {savedError && (
        <div className="flex items-center gap-3 border-y border-red-200 py-3 text-sm text-red-700 dark:border-red-900 dark:text-red-300" role="alert">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="flex-1">{practiceErrorMessage(savedError, "load")}</span>
          <Button variant="outline" size="sm" onClick={() => refetchSaved()}>Retry</Button>
        </div>
      )}
      {savedQuestions.length > 0 && (
        <section className="space-y-3 border-y border-border py-4" aria-labelledby="saved-order-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 id="saved-order-heading" className="font-semibold text-primary dark:text-foreground">Saved question order</h2>
              <p className="text-sm text-muted-foreground">Custom order is used for your next saved-question session. Without one, oldest saved questions come first.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {!orderDraft ? (
                <Button variant="outline" size="sm" onClick={() => setOrderDraft([...savedQuestions])}>
                  <ListOrdered className="mr-2 h-4 w-4" />Reorder
                </Button>
              ) : (
                <>
                  <Button variant="outline" size="sm" disabled={!orderChanged || savingOrder} onClick={() => void saveOrder()}>Save order</Button>
                  <Button variant="ghost" size="sm" disabled={savingOrder} onClick={() => setOrderDraft(null)}>Cancel</Button>
                </>
              )}
              {hasCustomOrder && (
                <Button variant="ghost" size="sm" disabled={savingOrder} onClick={() => void resetOrder()}>Reset order</Button>
              )}
            </div>
          </div>
          {orderError && <p className="text-sm text-red-700 dark:text-red-300" role="alert">{orderError}</p>}
          {orderDraft && (
            <ol className="divide-y divide-border border-y border-border">
              {orderedBookmarks.map((bookmark, index) => (
                <li key={bookmark.id} className="flex items-center gap-3 py-3">
                  <span className="w-7 shrink-0 text-sm tabular-nums text-muted-foreground">{index + 1}.</span>
                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-sm font-medium text-primary dark:text-foreground">{bookmark.question_detail.text}</p>
                    <time className="text-xs text-muted-foreground" dateTime={bookmark.saved_at}>
                      Saved {new Date(bookmark.saved_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}
                    </time>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" size="icon" aria-label={`Move saved question ${index + 1} up`} title="Move up" disabled={index === 0 || savingOrder} onClick={() => moveBookmark(index, -1)}><ArrowUp className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" aria-label={`Move saved question ${index + 1} down`} title="Move down" disabled={index === orderedBookmarks.length - 1 || savingOrder} onClick={() => moveBookmark(index, 1)}><ArrowDown className="h-4 w-4" /></Button>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
      <TopicPracticeBrowser
        key={session.session.id}
        initial={session}
        savedQuestionIds={savedIds}
        onToggleSave={toggle}
        onFinish={async () => {
          const result = await practiceApi.submitSession(session.session.id, 0);
          queryClient.setQueryData(practiceResultKey(session.session.id), result);
          router.push(`/student/practice/results/${session.session.id}`);
        }}
      />
    </main>
  );
}
