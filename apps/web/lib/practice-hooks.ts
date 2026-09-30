"use client";

import { useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useOptionalStudentContext } from "@/contexts/StudentContext";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { syllabusApi } from "@/lib/api/syllabus";
import { practiceApi, SavedQuestion } from "@/lib/api/practice";
import { notify } from "@/lib/notify";
import { practiceErrorMessage } from "@/lib/practice-errors";

// The syllabus tree and the saved-questions list are the same for every
// Practice screen, so they go through the app's existing React Query cache:
// Dashboard -> Practice -> Dashboard -> Practice shows the cached copy at
// once and revalidates it, instead of refetching from scratch each visit.
// Scoped to the signed-in student and the active course: the practice list is
// course-authorised, so switching courses must not reuse another course's tree.
export const practiceExamsKey = (userId: number | string | undefined, courseId?: number | null) => ["practice-exams", userId, courseId ?? "all"] as const;
export const SAVED_QUESTIONS_KEY = ["saved-questions"] as const;
export const REVISION_SUMMARY_KEY = ["revision-summary"] as const;
const savedQuestionsKey = (userId: number | string | undefined, courseId?: number | null) => [...SAVED_QUESTIONS_KEY, userId, courseId ?? "all"] as const;
export const practiceResultKey = (sessionId: number) => ["practice-result", sessionId] as const;

// The server returns only the exams this student is authorised to practise;
// nothing is fetched globally and filtered here. On failure there is no
// fallback list - callers show an error with Retry.
export function usePracticeExams(courseIdOverride?: number | null) {
  const { user } = useAuth();
  const studentCtx = useOptionalStudentContext();
  const effectiveCourseId = courseIdOverride ?? studentCtx?.activeCourse?.id ?? null;

  return useQuery({
    queryKey: practiceExamsKey(user?.id, effectiveCourseId),
    queryFn: () => syllabusApi.getExams(effectiveCourseId),
    enabled: !!user && (!studentCtx || !studentCtx.isLoading),
    staleTime: 5 * 60 * 1000,
  });
}

// One shared query, so two components asking for the revision counts (or a
// StrictMode double-mount) produce a single request.
export function useRevisionSummary(courseIdOverride?: number | null) {
  const { user } = useAuth();
  const studentCtx = useOptionalStudentContext();
  const courseId = courseIdOverride ?? studentCtx?.activeCourse?.id ?? null;
  return useQuery({
    queryKey: [...REVISION_SUMMARY_KEY, user?.id, courseId ?? "all"],
    queryFn: () => practiceApi.getRevisionSummary(courseId),
    enabled: !!user && (!studentCtx || !studentCtx.isLoading),
    staleTime: 30 * 1000,
  });
}

export function useSavedQuestions() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const studentCtx = useOptionalStudentContext();
  const courseId = studentCtx?.activeCourse?.id ?? null;
  const queryKey = savedQuestionsKey(user?.id, courseId);
  const query = useQuery({
    queryKey,
    queryFn: () => practiceApi.listSavedQuestions(courseId),
    enabled: !!user && (!studentCtx || !studentCtx.isLoading),
    staleTime: 60 * 1000,
  });

  const savedIds: Record<number, boolean> = {};
  (query.data ?? []).forEach((s: SavedQuestion) => {
    savedIds[s.question] = true;
  });

  // Optimistic toggle: flip the star immediately, put it back (and say why)
  // if the server refused.
  const toggle = useCallback(
    async (questionId: number) => {
      const previous = queryClient.getQueryData<SavedQuestion[]>(queryKey) ?? [];
      const wasSaved = previous.some((s) => s.question === questionId);
      queryClient.setQueryData<SavedQuestion[]>(
        queryKey,
        wasSaved
          ? previous.filter((s) => s.question !== questionId)
          : [...previous, { id: -questionId, question: questionId } as SavedQuestion]
      );
      try {
        await practiceApi.toggleBookmark(questionId, courseId);
      } catch (e) {
        queryClient.setQueryData(queryKey, previous);
        notify.error(practiceErrorMessage(e, "save"));
      }
    },
    [queryClient, queryKey, courseId]
  );

  return {
    savedIds,
    savedQuestions: query.data ?? [],
    toggle,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
  };
}
