import { ApiError } from "@/lib/api/client";

/**
 * One place that turns whatever a Practice request threw into a sentence a
 * student can act on. Raw status codes, Django detail strings and stack
 * traces never reach the screen.
 *
 * `kind` lets a caller decide how to react (offer Retry for `network` and
 * `server`, show an empty state for `no-questions`, and so on).
 */
export type PracticeErrorKind =
  | "network"
  | "unauthorized"
  | "forbidden"
  | "unavailable"
  | "completed"
  | "in-progress"
  | "no-questions"
  | "server"
  | "other";

export type PracticeErrorContext = "start" | "load" | "answer" | "reveal" | "submit" | "result" | "save";

export interface PracticeError {
  kind: PracticeErrorKind;
  message: string;
  /** Worth offering a Retry button: the same request may succeed next time. */
  retryable: boolean;
}

export const NETWORK_MESSAGE = "We couldn't connect to the server. Please check your connection and try again.";
export const UNAVAILABLE_MESSAGE = "This practice session is no longer available.";
export const NO_QUESTIONS_MESSAGE = "No questions are available for this practice yet.";
export const COMPLETED_MESSAGE = "You have already completed this practice.";
export const ANSWER_FAILED_MESSAGE = "Your answer could not be saved. Please try again.";

const FALLBACK: Record<PracticeErrorContext, string> = {
  start: "We couldn't start this practice. Please try again.",
  load: "We couldn't load these questions. Please try again.",
  answer: ANSWER_FAILED_MESSAGE,
  reveal: "We couldn't load the answer. Please try again.",
  submit: "We couldn't finish this practice. Please try again.",
  result: "We couldn't load your result. Please try again.",
  save: "We couldn't update your saved questions. Please try again.",
};

function isNetworkFailure(err: unknown): boolean {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return true;
  // fetch() rejects with a TypeError when the request never got a response
  // (offline, DNS, server down, CORS-blocked 5xx from a dead proxy).
  return err instanceof TypeError;
}

function backendDetail(err: ApiError): string {
  const d = err.data;
  const text = typeof d === "string" ? d : d?.detail || d?.error || "";
  return typeof text === "string" ? text.toLowerCase() : "";
}

export function practiceError(err: unknown, context: PracticeErrorContext = "load"): PracticeError {
  if (isNetworkFailure(err)) {
    return { kind: "network", message: NETWORK_MESSAGE, retryable: true };
  }

  if (err instanceof ApiError) {
    const detail = backendDetail(err);

    if (err.status === 401) {
      return { kind: "unauthorized", message: "Your session has expired. Please sign in again.", retryable: false };
    }
    if (err.status === 403) {
      // Course-access denials carry a sentence written for students; anything
      // else (including a package lock, which the API client redirects) gets
      // the generic wording.
      const d = err.data?.detail;
      const studentFacing =
        typeof d === "string" &&
        (detail.includes("not enrolled") || detail.includes("not available yet") || detail.includes("not part of"));
      return {
        kind: "forbidden",
        message: studentFacing ? d : "You don't have access to this practice.",
        retryable: false,
      };
    }
    if (err.status === 404) {
      // A missing question inside a session is an answer problem, a missing
      // session is "no longer available".
      if (context === "answer" || context === "reveal") {
        return { kind: "other", message: FALLBACK[context], retryable: true };
      }
      return { kind: "unavailable", message: UNAVAILABLE_MESSAGE, retryable: false };
    }
    if (err.status === 409) {
      return {
        kind: "in-progress",
        message: "This practice isn't finished yet. Finish it to see your result.",
        retryable: false,
      };
    }
    if (err.status === 400) {
      if (detail.includes("already completed")) {
        return { kind: "completed", message: COMPLETED_MESSAGE, retryable: false };
      }
      if (detail.includes("no approved questions") || detail.includes("no revision questions")
        || detail.includes("no practice questions") || detail.includes("no saved questions")) {
        return { kind: "no-questions", message: NO_QUESTIONS_MESSAGE, retryable: false };
      }
      return { kind: "other", message: FALLBACK[context], retryable: true };
    }
    if (err.status >= 500) {
      return {
        kind: "server",
        message: "Something went wrong on our side. Please try again in a moment.",
        retryable: true,
      };
    }
  }

  return { kind: "other", message: FALLBACK[context], retryable: true };
}

/** Convenience for callers that only need the sentence. */
export const practiceErrorMessage = (err: unknown, context: PracticeErrorContext = "load") =>
  practiceError(err, context).message;
