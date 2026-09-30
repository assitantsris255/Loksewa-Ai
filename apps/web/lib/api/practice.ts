import { apiClient } from "./client";
export interface Question {
  id: number;
  canonical_number?: number;
  text: string;
  option_a: string;
  option_b: string;
  option_c: string;
  option_d: string;
  difficulty: string;
  hint?: string;
  correct_option?: string;
  explanation?: string;
}

export interface StartSessionParams {
  course?: number | null;
  exam: string;
  subject: string;
  topic: string;
  difficulty: string;
  mode: string;
  total_questions: number;
}

export interface PracticeSession {
  id: number;
  user: number;
  exam: number;
  subject: number | null;
  topic: number | null;
  mode: string;
  shuffle_questions: boolean;
  difficulty: string | null;
  total_questions: number;
  correct_count: number;
  incorrect_count: number;
  unanswered_count: number;
  score: number;
  accuracy: number;
  time_taken_seconds: number;
  completed: boolean;
  created_at: string;
}

export interface PracticeSessionResponse {
  session: PracticeSession;
  questions: Question[]; // This will be SecureQuestionSerializer output initially
}

// The signal key maps to a human-readable label
export const REVISION_SIGNAL_LABELS: Record<string, string> = {
  overdue: "Due for review",
  repeatedly_incorrect: "Repeated mistake",
  recent_mistakes: "Recent mistake",
  weak_topics: "Weak topic",
};

export interface RevisionSessionResponse extends PracticeSessionResponse {
  // question_id (string key from JSON) -> signal key
  question_signals: Record<string, string>;
}

export interface SaveAnswerParams {
  question_id: number;
  selected_option: string | null;
  is_marked_for_review: boolean;
}

export interface AttemptDetail {
  attempt_id: number;
  question: Question;
  selected_option: string | null;
  is_correct: boolean;
  is_marked_for_review: boolean;
}

export interface SubmitSessionResponse {
  session: PracticeSession;
  attempts: AttemptDetail[];
}

export interface SavedQuestion {
  id: number;
  question: number;
  question_detail: Question & { topic: number };
  created_at: string;
  saved_at: string;
  custom_order: number | null;
}

export interface AnswerResult {
  status: string;
  // Present when the mode scores immediately (study/revision) — absent for
  // flexible/timed practice, which is only scored at final submit.
  is_correct?: boolean;
  correct_option?: string;
  explanation?: string;
  // True when the same question was already answered: the server kept the
  // first answer and returned it (retries and second tabs are harmless).
  already_answered?: boolean;
  // The option the server holds for this question (differs from the one
  // just sent when the first answer was kept).
  selected_option?: string | null;
}

export interface RevealResult {
  correct_option: string;
  explanation: string;
}

export interface AttemptState {
  question_id: number;
  selected_option: string | null;
  is_correct: boolean | null;
  is_viewed: boolean;
  correct_option?: string;
  explanation?: string;
}

export interface StudySessionResponse extends PracticeSessionResponse {
  attempts: AttemptState[];
  resume_index: number;
  resumed: boolean;
}

// Whole-session totals from the server - never derived from the loaded page.
export interface StudyStats {
  total: number;
  answered: number;
  correct: number;
  wrong: number;
  accuracy: number;
}

// One page of a Topic-wise session: only these questions are sent.
export interface StudyPage {
  session: PracticeSession;
  questions: Question[];
  attempts: AttemptState[];
  page: number; // 1-based
  page_size: number;
  total_pages: number;
  total_questions: number;
  first_index: number; // 0-based index of this page's first question
  stats: StudyStats;
  resumed?: boolean;
  resume_index?: number;
}

export interface RevisionSummary {
  overdue: number;
  repeatedly_incorrect: number;
  recent_mistakes: number;
  weak_topics: number;
  total_available: number;
}

export type RevisionFocus = "overdue" | "repeatedly_incorrect" | "recent_mistakes" | "weak_topics";

export const practiceApi = {
  startSession: (params: StartSessionParams) => {
    return apiClient<PracticeSessionResponse>("/practice-sessions/", {
      method: "POST",
      body: JSON.stringify(params),
    });
  },
  
  saveAnswer: (sessionId: number, params: SaveAnswerParams) => {
    return apiClient<AnswerResult>(`/practice-sessions/${sessionId}/answer/`, {
      method: "POST",
      body: JSON.stringify(params),
    });
  },

  markViewed: (sessionId: number, questionId: number) => {
    return apiClient<{status: string}>(`/practice-sessions/${sessionId}/view/`, {
      method: "POST",
      body: JSON.stringify({ question_id: questionId }),
    });
  },

  reveal: (sessionId: number, questionId: number) => {
    return apiClient<RevealResult>(`/practice-sessions/${sessionId}/reveal/`, {
      method: "POST",
      body: JSON.stringify({ question_id: questionId }),
    });
  },

  startStudy: (params: {
    topic: string | number;
    subject?: string;
    exam?: string;
    course?: number | null;
    shuffle_questions?: boolean;
    restart?: boolean;
    page?: number;
    page_size?: number;
  }) => {
    return apiClient<StudyPage>("/practice-sessions/study/", {
      method: "POST",
      body: JSON.stringify(params),
    });
  },

  startSavedSession: (courseId?: number | null) => {
    return apiClient<StudyPage>("/practice-sessions/saved/", {
      method: "POST",
      body: JSON.stringify({ course_id: courseId ?? undefined }),
    });
  },

  getStudyPage: (sessionId: number, page: number, pageSize: number) => {
    return apiClient<StudyPage>(
      `/practice-sessions/${sessionId}/questions/?page=${page}&page_size=${pageSize}`
    );
  },

  getRevisionSummary: (courseId?: number | null) => {
    const query = courseId == null ? "" : `?course_id=${courseId}`;
    return apiClient<RevisionSummary>(`/practice-sessions/revision_summary/${query}`);
  },

  startRevision: (focus?: RevisionFocus, courseId?: number | null) => {
    return apiClient<RevisionSessionResponse>("/practice-sessions/start_revision/", {
      method: "POST",
      body: JSON.stringify({
        ...(focus ? { focus } : {}),
        ...(courseId == null ? {} : { course_id: courseId }),
      }),
    });
  },
  
  submitSession: (sessionId: number, time_taken_seconds: number) => {
    return apiClient<SubmitSessionResponse>(`/practice-sessions/${sessionId}/submit/`, {
      method: "POST",
      body: JSON.stringify({ time_taken_seconds }),
    });
  },

  // Read-only: opening or refreshing a result never completes a session (that
  // used to happen because this called submit). Answers 409 while the session
  // is still in progress.
  getSessionResult: (sessionId: number) => {
    return apiClient<SubmitSessionResponse>(`/practice-sessions/${sessionId}/result/`);
  },

  toggleBookmark: (questionId: number, courseId?: number | null) => {
    return apiClient<{status: string; id?: number}>("/bookmarks/", {
      method: "POST",
      body: JSON.stringify({ question_id: questionId, course_id: courseId ?? undefined }),
    });
  },

  startDailySession: () => {
    return apiClient<StudySessionResponse>("/practice-sessions/daily/", {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  listSavedQuestions: (courseId?: number | null) => {
    const query = courseId == null ? "" : `?course_id=${courseId}`;
    return apiClient<SavedQuestion[]>(`/bookmarks/${query}`);
  },

  orderSavedQuestions: (bookmarkIds: number[], courseId?: number | null) => {
    const query = courseId == null ? "" : `?course_id=${courseId}`;
    return apiClient<{ status: string; count: number }>(`/bookmarks/order/${query}`, {
      method: "PATCH",
      body: JSON.stringify({ bookmark_ids: bookmarkIds }),
    });
  },

  resetSavedQuestionOrder: (courseId?: number | null) => {
    const query = courseId == null ? "" : `?course_id=${courseId}`;
    return apiClient<{ status: string; count: number }>(`/bookmarks/reset-order/${query}`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },
};
