"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { practiceApi, StudyPage, StudyStats, Question, AttemptState } from "@/lib/api/practice";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Star, CheckCircle2, XCircle, AlertCircle, Flag, Lightbulb, RotateCcw } from "lucide-react";
import { practiceError, practiceErrorMessage, ANSWER_FAILED_MESSAGE, NO_QUESTIONS_MESSAGE } from "@/lib/practice-errors";
import { REVISION_SUMMARY_KEY } from "@/lib/practice-hooks";

interface QuestionState {
  selected_option?: string;
  is_correct?: boolean | null;
  is_viewed: boolean;
  correct_option?: string;
  explanation?: string;
  error?: string;
  saving?: boolean;
}

interface TopicPracticeBrowserProps {
  /** The page the start/resume request already returned. */
  initial: StudyPage;
  savedQuestionIds: Record<number, boolean>;
  onToggleSave: (questionId: number) => void;
  onFinish: () => void | Promise<void>;
}

const PAGE_SIZE_OPTIONS = [10, 20] as const;
export const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_STORAGE_KEY = "loksewa.topicPractice.pageSize";

/** The student's remembered 10/20 choice (a per-viewer convenience only). */
export function readStoredPageSize(): number {
  try {
    const stored = Number(localStorage.getItem(PAGE_SIZE_STORAGE_KEY));
    if (stored === 10 || stored === 20) return stored;
  } catch {
    // localStorage unavailable - keep the default
  }
  return DEFAULT_PAGE_SIZE;
}

function toStateMap(attempts: AttemptState[]): Record<number, QuestionState> {
  const map: Record<number, QuestionState> = {};
  attempts.forEach((a) => {
    map[a.question_id] = {
      selected_option: a.selected_option || undefined,
      is_correct: a.is_correct,
      is_viewed: a.is_viewed,
      correct_option: a.correct_option,
      explanation: a.explanation,
    };
  });
  return map;
}

export function QuestionSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading questions">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-card rounded-[16px] border border-border shadow-sm p-6 md:p-8 animate-pulse">
          <div className="h-3 w-24 rounded bg-muted mb-6" />
          <div className="h-5 w-3/4 rounded bg-muted mb-3" />
          <div className="h-5 w-1/2 rounded bg-muted mb-8" />
          <div className="space-y-4">
            {[0, 1, 2, 3].map((o) => (
              <div key={o} className="h-14 rounded-[12px] border-2 border-border bg-muted/40" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function TopicPracticeBrowser({ initial, savedQuestionIds, onToggleSave, onFinish }: TopicPracticeBrowserProps) {
  const sessionId = initial.session.id;
  const queryClient = useQueryClient();

  const [pageSize, setPageSize] = useState<number>(initial.page_size);
  const [page, setPage] = useState<number>(initial.page);
  const [state, setState] = useState<Record<number, QuestionState>>(() => toStateMap(initial.attempts));
  const [visibleHints, setVisibleHints] = useState<Record<number, boolean>>({});
  const [stats, setStats] = useState<StudyStats>(initial.stats);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState<string | null>(null);
  // Synchronous guard against double clicks: setState is async, so two clicks
  // in the same tick would both pass a `state`-based check.
  const inFlight = useRef<Set<number>>(new Set());
  // When the student last changed something locally. A page fetched (or
  // prefetched) BEFORE that moment carries older totals and must not
  // overwrite the live numbers.
  const lastChangeAt = useRef(0);

  const pageQuery = useQuery({
    queryKey: ["practice-study-page", sessionId, page, pageSize],
    queryFn: () => practiceApi.getStudyPage(sessionId, page, pageSize),
    // The page the start request returned is already in hand - no refetch.
    initialData: page === initial.page && pageSize === initial.page_size ? initial : undefined,
    staleTime: 60 * 1000,
    retry: false,
  });
  const data = pageQuery.data;

  // Fold a fetched page's saved state in without ever overwriting an answer
  // the student has just given on screen.
  useEffect(() => {
    if (!data) return;
    setState((prev) => {
      const fromServer = toStateMap(data.attempts);
      const merged = { ...fromServer };
      Object.keys(prev).forEach((k) => {
        const id = Number(k);
        if (prev[id]?.is_viewed || prev[id]?.saving || prev[id]?.error) merged[id] = prev[id]!;
      });
      return merged;
    });
    if (pageQuery.dataUpdatedAt > lastChangeAt.current) setStats(data.stats);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // Warm the next page so "Next Page" is instant.
  useEffect(() => {
    if (!data || data.page >= data.total_pages) return;
    queryClient.prefetchQuery({
      queryKey: ["practice-study-page", sessionId, data.page + 1, pageSize],
      queryFn: () => practiceApi.getStudyPage(sessionId, data.page + 1, pageSize),
      staleTime: 60 * 1000,
    });
  }, [data, queryClient, sessionId, pageSize]);

  const changePageSize = (size: number) => {
    if (size === pageSize) return;
    setPageSize(size);
    setPage(1);
    try {
      localStorage.setItem(PAGE_SIZE_STORAGE_KEY, String(size));
    } catch {
      // ignore - per-viewer convenience only
    }
  };

  const applyAnswerToStats = (isCorrect: boolean) => {
    lastChangeAt.current = Date.now();
    setStats((s) => {
      const answered = s.answered + 1;
      const correct = s.correct + (isCorrect ? 1 : 0);
      return { ...s, answered, correct, wrong: answered - correct, accuracy: Math.round((correct / answered) * 100) };
    });
  };

  const handleSelect = async (q: Question, opt: string) => {
    if (state[q.id]?.is_viewed || inFlight.current.has(q.id)) return; // locked in / already sending
    inFlight.current.add(q.id);
    setState((prev) => ({
      ...prev,
      [q.id]: { ...prev[q.id], is_viewed: false, selected_option: opt, saving: true, error: undefined },
    }));
    try {
      const result = await practiceApi.saveAnswer(sessionId, {
        question_id: q.id,
        selected_option: opt,
        is_marked_for_review: false,
      });
      // The server is the source of truth: if this question was already
      // answered (retry, second tab) it returns the stored answer instead.
      setState((prev) => ({
        ...prev,
        [q.id]: {
          selected_option: result.selected_option ?? opt,
          is_correct: result.is_correct ?? null,
          is_viewed: true,
          correct_option: result.correct_option,
          explanation: result.explanation,
          saving: false,
        },
      }));
      if (result.is_correct !== undefined) applyAnswerToStats(!!result.is_correct);
      // A cached copy of this page predates the answer, and the answer
      // feeds the revision queue counts shown on the Practice screen.
      queryClient.invalidateQueries({ queryKey: ["practice-study-page", sessionId], refetchType: "none" });
      queryClient.invalidateQueries({ queryKey: REVISION_SUMMARY_KEY, refetchType: "none" });
    } catch (e) {
      console.error(e);
      // Do NOT mark the answer as saved: the option stays highlighted so
      // the student can see what they picked, with an explicit Retry.
      setState((prev) => ({
        ...prev,
        [q.id]: {
          ...prev[q.id],
          is_viewed: false,
          selected_option: opt,
          saving: false,
          error: practiceError(e, "answer").kind === "network"
            ? practiceErrorMessage(e, "answer")
            : ANSWER_FAILED_MESSAGE,
        },
      }));
    } finally {
      inFlight.current.delete(q.id);
    }
  };

  const handleShowAnswer = async (q: Question) => {
    if (state[q.id]?.is_viewed || inFlight.current.has(q.id)) return;
    inFlight.current.add(q.id);
    setState((prev) => ({ ...prev, [q.id]: { ...prev[q.id], is_viewed: false, saving: true, error: undefined } }));
    try {
      const result = await practiceApi.reveal(sessionId, q.id);
      setState((prev) => ({
        ...prev,
        [q.id]: {
          ...prev[q.id],
          is_viewed: true,
          correct_option: result.correct_option,
          explanation: result.explanation,
          saving: false,
        },
      }));
      queryClient.invalidateQueries({ queryKey: ["practice-study-page", sessionId], refetchType: "none" });
    } catch (e) {
      console.error(e);
      setState((prev) => ({
        ...prev,
        [q.id]: { ...prev[q.id], is_viewed: false, saving: false, error: practiceErrorMessage(e, "reveal") },
      }));
    } finally {
      inFlight.current.delete(q.id);
    }
  };

  const handleFinish = async () => {
    setFinishing(true);
    setFinishError(null);
    try {
      await onFinish();
    } catch (e) {
      setFinishError(practiceErrorMessage(e, "submit"));
    } finally {
      setFinishing(false);
    }
  };

  const total = data?.total_questions ?? initial.total_questions;
  if (total === 0) {
    return <div className="p-8 text-center text-muted-foreground">{NO_QUESTIONS_MESSAGE}</div>;
  }

  const totalPages = data?.total_pages ?? Math.max(1, Math.ceil(total / pageSize));
  const isLastPage = page >= totalPages;
  const firstIndex = data?.first_index ?? (page - 1) * pageSize;
  const pageQuestions = data?.questions ?? [];

  return (
    <div className="max-w-[860px] mx-auto space-y-6 pb-8">
      {/* Progress + page-size controls - whole-session numbers from the server */}
      <div className="bg-card rounded-[16px] border border-border shadow-sm p-4 md:p-5 sticky top-2 z-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className="text-sm font-bold text-primary dark:text-foreground">
              Questions {firstIndex + 1}–{Math.min(firstIndex + pageSize, total)} of {total}
            </span>
          </div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <span>Per page:</span>
            {PAGE_SIZE_OPTIONS.map((size) => (
              <button
                key={size}
                type="button"
                onClick={() => changePageSize(size)}
                className={`px-2.5 py-1 rounded-full border ${pageSize === size ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:bg-muted"}`}
              >
                {size}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-3 grid grid-cols-4 gap-2 text-center">
          <div>
            <div className="text-lg font-black text-primary dark:text-foreground">{stats.answered}/{total}</div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Answered</div>
          </div>
          <div>
            <div className="text-lg font-black text-green-600">{stats.correct}</div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Correct</div>
          </div>
          <div>
            <div className="text-lg font-black text-red-600">{stats.wrong}</div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Wrong</div>
          </div>
          <div>
            <div className="text-lg font-black text-[#D4A72C]">{stats.accuracy}%</div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Accuracy</div>
          </div>
        </div>
      </div>

      {/* Only the question area shows a loading / error state - the header
          and navigation stay put. */}
      {!data && pageQuery.isError ? (
        <div className="bg-card rounded-[16px] border border-border shadow-sm p-8 text-center space-y-4" role="alert">
          <AlertCircle className="w-8 h-8 text-red-500 mx-auto" aria-hidden="true" />
          <p className="text-[15px] font-medium text-primary dark:text-foreground">
            {practiceErrorMessage(pageQuery.error, "load")}
          </p>
          <Button variant="outline" onClick={() => pageQuery.refetch()}>
            <RotateCcw className="w-4 h-4 mr-2" /> Retry
          </Button>
        </div>
      ) : !data ? (
        <QuestionSkeleton count={3} />
      ) : (
        pageQuestions.map((q, idx) => {
          const qState = state[q.id];
          const isSaved = !!savedQuestionIds[q.id];
          const globalNumber = firstIndex + idx + 1;
          const canonicalNumber = q.canonical_number ?? globalNumber;
          const isEvaluated = !!qState?.is_viewed;

          return (
            <div key={q.id} className="bg-card rounded-[16px] border border-border shadow-sm p-6 md:p-8">
              <div className="flex justify-between items-center mb-6">
                <span className="text-sm font-bold text-muted-foreground tracking-widest uppercase">
                  Question {canonicalNumber}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onToggleSave(q.id)}
                  className={isSaved ? "text-[#D4A72C]" : "text-muted-foreground"}
                >
                  <Star className="w-4 h-4 mr-2" fill={isSaved ? "currentColor" : "none"} />
                  {isSaved ? "Saved" : "Save"}
                </Button>
              </div>

              <h2 className="text-xl font-medium text-primary dark:text-foreground leading-relaxed mb-8">{q.text}</h2>

              {q.hint && (
                <div className="mb-5">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setVisibleHints((prev) => ({ ...prev, [q.id]: !prev[q.id] }))}
                  >
                    <Lightbulb className="mr-2 h-4 w-4" />{visibleHints[q.id] ? "Hide Hint" : "Show Hint"}
                  </Button>
                  {visibleHints[q.id] && <p className="mt-2 border-l-2 border-amber-500 px-3 py-2 text-sm text-muted-foreground">{q.hint}</p>}
                </div>
              )}

              {isEvaluated && qState?.selected_option && (
                <div
                  className={`mb-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-bold ${
                    qState.is_correct
                      ? "bg-green-50 text-green-700 dark:bg-green-950/30 dark:text-green-400"
                      : "bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-400"
                  }`}
                  role="status"
                >
                  {qState.is_correct ? (
                    <>
                      <CheckCircle2 className="w-4 h-4" aria-hidden="true" /> Correct Answer
                    </>
                  ) : (
                    <>
                      <XCircle className="w-4 h-4" aria-hidden="true" /> Incorrect Answer
                    </>
                  )}
                </div>
              )}

              <fieldset className="space-y-4" disabled={qState?.saving} role="radiogroup">
                <legend className="sr-only">Answer options for question {canonicalNumber}</legend>
                {(["a", "b", "c", "d"] as const).map((opt) => {
                  const optionText = q[`option_${opt}`];
                  if (!optionText) return null;
                  const isSelected = qState?.selected_option === opt;
                  const isCorrectOption = qState?.correct_option?.toLowerCase() === opt;

                  let cls = "border-border bg-card hover:border-border hover:bg-muted";
                  let icon = null;
                  let stateLabel = "";
                  if (isEvaluated) {
                    if (isCorrectOption) {
                      cls = "border-green-300 bg-green-50 dark:bg-green-950/30 dark:border-green-900/50";
                      icon = <CheckCircle2 className="w-4 h-4 text-green-600 ml-auto shrink-0" aria-hidden="true" />;
                      stateLabel = " — correct answer";
                    } else if (isSelected) {
                      cls = "border-red-300 bg-red-50 dark:bg-red-950/30 dark:border-red-900/50";
                      icon = <XCircle className="w-4 h-4 text-red-600 ml-auto shrink-0" aria-hidden="true" />;
                      stateLabel = " — your answer, incorrect";
                    }
                  } else if (isSelected) {
                    cls = "border-[#0B2545] bg-muted";
                  }

                  return (
                    <button
                      key={opt}
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      aria-label={`Option ${opt.toUpperCase()}: ${optionText}${stateLabel}`}
                      onClick={() => handleSelect(q, opt)}
                      disabled={isEvaluated}
                      className={`w-full flex items-center p-4 rounded-[12px] border-2 transition-all text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B2545] focus-visible:ring-offset-2 ${cls} ${isEvaluated ? "cursor-default" : ""}`}
                    >
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center mr-4 font-bold text-sm shrink-0 ${
                          isSelected && !isEvaluated
                            ? "bg-primary text-primary-foreground text-white"
                            : "bg-muted/80 text-muted-foreground"
                        }`}
                      >
                        {opt.toUpperCase()}
                      </div>
                      <span className="text-[15px] font-medium text-primary dark:text-foreground">{optionText}</span>
                      {icon}
                    </button>
                  );
                })}
              </fieldset>

              {qState?.error && (
                <div className="mt-4 flex items-center gap-2 text-sm font-medium text-red-600" role="alert">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{qState.error}</span>
                  <button
                    type="button"
                    className="underline font-bold"
                    onClick={() => (qState.selected_option ? handleSelect(q, qState.selected_option) : handleShowAnswer(q))}
                  >
                    Retry
                  </button>
                </div>
              )}

              {!isEvaluated && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-6"
                  onClick={() => handleShowAnswer(q)}
                  disabled={qState?.saving}
                >
                  {qState?.saving ? "Saving..." : "View Answer"}
                </Button>
              )}

              {isEvaluated && qState?.explanation && (
                <p className="mt-6 text-[13.5px] text-muted-foreground bg-muted/40 rounded-[10px] p-4">
                  <strong className="text-primary dark:text-foreground">Explanation: </strong>
                  {qState.explanation}
                </p>
              )}
            </div>
          );
        })
      )}

      {finishError && (
        <p className="text-sm font-medium text-red-600 text-center" role="alert">
          {finishError}
        </p>
      )}

      {/* Page navigation */}
      <div className="flex justify-between items-center bg-card p-4 rounded-[16px] border border-border shadow-sm">
        <Button
          variant="outline"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
          className="h-12 px-6 rounded-[10px]"
        >
          <ChevronLeft className="w-4 h-4 mr-2" /> Previous
        </Button>
        <span className="text-sm font-bold text-muted-foreground">
          Page {page} of {totalPages}
        </span>
        {isLastPage ? (
          <Button
            onClick={handleFinish}
            disabled={finishing}
            className="h-12 px-6 rounded-[10px] bg-primary text-primary-foreground hover:bg-[#163E6B]"
          >
            <Flag className="w-4 h-4 mr-2" /> {finishing ? "Finishing..." : "Finish Practice"}
          </Button>
        ) : (
          <Button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="h-12 px-6 rounded-[10px] bg-primary text-primary-foreground hover:bg-[#163E6B]"
          >
            Next Page <ChevronRight className="w-4 h-4 ml-2" />
          </Button>
        )}
      </div>
    </div>
  );
}
