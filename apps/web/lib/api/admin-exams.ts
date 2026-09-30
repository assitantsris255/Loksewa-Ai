import { apiClient } from './client';

export interface EligibilityRule {
  id: number;
  target_category?: number;
  target_position?: number;
  is_global: boolean;
}

/** Examination.EXAM_TYPES in exams/models.py. */
export type ExaminationType =
  | 'mock'
  | 'practice'
  | 'full'
  | 'position'
  | 'subject'
  | 'custom'
  | 'subjective';

/**
 * Examination.STATUS_CHOICES in exams/models.py, plus the three lifecycle
 * values that ExaminationViewSet.publish() writes ('scheduled' | 'live' |
 * 'completed') which are not declared in the model's choices.
 */
export type ExaminationStatus =
  | 'draft'
  | 'pending_review'
  | 'approved'
  | 'published'
  | 'changes_requested'
  | 'rejected'
  | 'archived'
  | 'scheduled'
  | 'live'
  | 'completed';

/** Examination.OBJECTIVE_CATEGORIES in exams/models.py — the four finalized
 * Objective Exam categories. Null/blank for non-objective exam_types like
 * 'subjective', and for exams created before this field existed. */
export type ObjectiveCategory = 'past_year' | 'model' | 'live' | 'topicwise' | null;

export interface Examination {
  id: number;
  title: string;
  description: string;
  exam_type: ExaminationType;
  objective_category: ObjectiveCategory;
  category: number;
  category_name?: string;
  course?: number | null;
  course_title?: string;
  exam: number;
  exam_name?: string;
  subject: number;
  subject_name?: string;
  topic?: number | null;
  topic_name?: string | null;
  question_set?: number;
  question_set_name?: string;
  instructions: string;
  thumbnail?: string;
  total_questions: number;
  time_limit: number;
  total_marks: number;
  passing_marks: number;
  marks_per_question: number;
  negative_marking: boolean;
  negative_marking_value: number;
  max_attempts: number;
  allow_resume: boolean;
  auto_submit: boolean;
  result_visibility: 'immediate' | 'after_end' | 'manual';
  show_correct_answers: boolean;
  randomize_questions: boolean;
  randomize_options: boolean;
  start_time?: string;
  end_time?: string;
  status: ExaminationStatus;
  created_at: string;
  updated_at: string;
  eligibility_rules: EligibilityRule[];
  attempts_count: number;
  // Subjective examination fields
  question_paper_pdf?: string | null;
  question_paper_page_count?: number;
  question_paper_file_size?: number;
  answer_upload_enabled?: boolean;
  upload_deadline_minutes?: number;
  upload_start_time?: string | null;
  upload_end_time?: string | null;
  allowed_file_types?: string;
  max_upload_size_mb?: number;
  evaluation_type?: 'admin' | 'manual' | 'ai' | 'ai_assisted' | 'hybrid';
}

export interface AdminCourseOption {
  id: number;
  title: string;
  exam: {
    id: number;
    category_id: number | null;
  } | null;
}

export interface AdminSubjectiveSubmission {
  id: number;
  attempt_id: number;
  student_id: number;
  student_name: string;
  student_username: string;
  student_email: string;
  examination_id: number;
  examination_title: string;
  status: string;
  attempt_status: string;
  started_at: string;
  submitted_at: string | null;
  page_count: number;
  file_size_bytes: number;
  has_answer_pdf: boolean;
  is_pdf?: boolean;
  file_name?: string;
  score: number;
  total_marks: number;
  percentage: number;
  ocr_status: string;
  evaluator: number | null;
  evaluator_name: string | null;
  evaluated_at: string | null;
  is_published: boolean;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubjectiveSubmissionPage {
  id: number;
  page_number: number;
  image_url: string;
  file_size_bytes: number;
  created_at: string;
}

export interface SubjectiveQuestionScore {
  id: number;
  question_number: number;
  marks_obtained: number;
  max_marks: number;
  feedback: string;
}

export interface AdminSubjectiveSubmissionDetail extends AdminSubjectiveSubmission {
  time_taken_seconds: number;
  raw_ocr_text: string;
  extracted_text: string;
  ocr_error: string;
  evaluator_feedback: string;
  pages: SubjectiveSubmissionPage[];
  question_scores: SubjectiveQuestionScore[];
}

export interface AdminExaminationRequest {
  id: number;
  request_type: 'exam_access' | 'subjective_live';
  student: number;
  student_name: string;
  examination: number;
  examination_title: string;
  examination_status: string | null;
  academic_exam: number | null;
  requested_exam_name: string | null;
  course: number | null;
  requested_course_title: string | null;
  subject: number | null;
  requested_subject_name: string | null;
  topic: number | null;
  requested_topic_name: string | null;
  status: 'pending' | 'approved' | 'rejected';
  rejection_reason: string;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface SubjectivePaperGenerationResult {
  id: number;
  title: string;
  status: string;
  total_questions: number;
  total_marks: number;
  time_limit?: number;
  has_question_paper: boolean;
  question_paper_page_count?: number;
  question_paper_file_size?: number;
  reused: boolean;
}

export interface ExamQueryParams {
  search?: string;
  exam_type?: string;
  status?: string;
  category?: number;
  exam?: number;
  subject?: number;
}

/* ------------------------------------------------------------------ *
 * Examination Analytics
 * GET /api/admin/exams/{id}/analytics/
 * Shape mirrors administration/exam_views.py :: ExaminationViewSet.analytics
 * ------------------------------------------------------------------ */

export type ExamDifficulty = 'easy' | 'medium' | 'hard';

/** Compact examination descriptor embedded in the analytics payload. */
export interface ExamAnalyticsExam {
  id: number;
  title: string;
  exam_type: string;
  status: string;
}

/**
 * When the examination has zero attempts the backend short-circuits and only
 * returns the three counters below (plus `message`), so every aggregated
 * metric is optional by design — it is not a "maybe missing" field.
 */
export interface ExamAnalyticsSummary {
  total_attempts: number;
  completed_attempts: number;
  in_progress_attempts: number;
  average_score?: number;
  average_percentage?: number;
  highest_score?: number;
  lowest_score?: number;
  pass_count?: number;
  fail_count?: number;
}

export interface ExamTimeStatistics {
  average_duration_seconds: number;
  /** Django Min() returns null when there are no evaluated attempts. */
  min_duration_seconds: number | null;
  max_duration_seconds: number | null;
}

export interface ExamScoreDistributionBucket {
  /** Pre-formatted decile label produced by the backend, e.g. "40-50%". */
  range: string;
  count: number;
}

export interface ExamQuestionPerformance {
  question_id: number;
  question_number: number;
  /** Truncated to 100 chars by the backend. */
  question_text: string;
  total_responses: number;
  correct: number;
  incorrect: number;
  skipped: number;
  accuracy: number;
  difficulty: ExamDifficulty;
}

export interface ExamDifficultyPerformance {
  /** Capitalised by the backend: "Easy" | "Medium" | "Hard". */
  level: string;
  /** Number of recorded responses at this difficulty (not distinct students). */
  attempts: number;
  accuracy: number;
}

export interface ExamAnalyticsResponse {
  exam: ExamAnalyticsExam;
  summary: ExamAnalyticsSummary;
  /** Only present on the "no attempts yet" response. */
  message?: string;
  time_statistics?: ExamTimeStatistics;
  score_distribution?: ExamScoreDistributionBucket[];
  question_performance?: ExamQuestionPerformance[];
  difficulty_performance?: ExamDifficultyPerformance[];
}

/* ------------------------------------------------------------------ *
 * Examination Results
 * GET /api/admin/exams/{id}/results/
 * Shape mirrors administration/exam_views.py :: ExaminationViewSet.results
 * ------------------------------------------------------------------ */

export type ExamAttemptStatus = 'in-progress' | 'submitted' | 'evaluated';

export interface ExamResultRow {
  id: number;
  student_id: number;
  student_name: string;
  email: string;
  started_at: string;
  submitted_at: string | null;
  status: ExamAttemptStatus;
  score: number;
  percentage: number;
  passed: boolean;
  time_taken_seconds: number;
  correct_answers: number;
  incorrect_answers: number;
  skipped_answers: number;
  /** Null while the attempt has not been evaluated. */
  rank: number | null;
}

export interface ExamResultsResponse {
  count: number;
  /** Absent on the backend's out-of-range fallback response. */
  num_pages?: number;
  current_page?: number;
  results: ExamResultRow[];
}

/** Only orderings backed by real columns on ExaminationAttempt. */
export type ExamResultsOrdering =
  | '-score'
  | 'score'
  | '-percentage'
  | 'percentage'
  | 'time_taken_seconds'
  | '-time_taken_seconds'
  | '-submitted_at'
  | 'submitted_at';

export interface ExamResultsQueryParams {
  page?: number;
  page_size?: number;
  passed?: boolean;
  status?: ExamAttemptStatus;
  search?: string;
  ordering?: ExamResultsOrdering;
}

function buildQueryString(params?: object): string {
  if (!params) return '';
  const searchParams = new URLSearchParams();
  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    searchParams.append(key, String(value));
  });
  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

export const adminExamApi = {
  getPublishedCourses: async () =>
    apiClient<AdminCourseOption[]>("/courses/public/?status=published"),

  getOverview: async () => {
    return apiClient<any>(`/admin/exams-overview/`);
  },

  getExams: async (params?: ExamQueryParams) => {
    let queryString = "";
    if (params) {
      const searchParams = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          searchParams.append(key, String(value));
        }
      });
      const queryStr = searchParams.toString();
      if (queryStr) {
        queryString = `?${queryStr}`;
      }
    }
    return apiClient<{ count: number; next: string | null; previous: string | null; results: Examination[] }>(`/admin/exams/${queryString}`);
  },

  getExamRequests: (status?: AdminExaminationRequest['status']) =>
    apiClient<AdminExaminationRequest[]>(`/admin/exam-requests/${buildQueryString({ status })}`),

  getExamRequest: (id: number) => apiClient<AdminExaminationRequest>(`/admin/exam-requests/${id}/`),

  approveExamRequest: (id: number) =>
    apiClient<AdminExaminationRequest>(`/admin/exam-requests/${id}/approve/`, { method: 'POST' }),

  rejectExamRequest: (id: number, rejection_reason: string) =>
    apiClient<AdminExaminationRequest>(`/admin/exam-requests/${id}/reject/`, {
      method: 'POST',
      body: JSON.stringify({ rejection_reason }),
    }),

  getExam: async (id: number) => {
    return apiClient<Examination>(`/admin/exams/${id}/`);
  },

  generateSubjectiveLiveExam: (payload: {
    generation_key: string;
    request_id?: number;
    exam: number;
    course?: number;
    subject?: number;
    topic?: number;
    title?: string;
    question_count: number;
    time_limit: number;
    start_time?: string | null;
    end_time?: string | null;
    instructions?: string;
    question_type: 'subjective' | 'objective' | 'mixed' | 'mcq' | 'true_false';
    regenerate?: boolean;
  }) => apiClient<SubjectivePaperGenerationResult>('/admin/exams/generate-subjective-live/', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),

  createExam: async (data: Partial<Examination>) => {
    return apiClient<Examination>('/admin/exams/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  updateExam: async (id: number, data: Partial<Examination>) => {
    return apiClient<Examination>(`/admin/exams/${id}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  },

  deleteExam: async (id: number) => {
    return apiClient(`/admin/exams/${id}/`, {
      method: 'DELETE',
    });
  },

  duplicateExam: async (id: number) => {
    return apiClient<Examination>(`/admin/exams/${id}/duplicate/`, {
      method: 'POST',
    });
  },

  publishExam: async (id: number) => {
    return apiClient<Examination>(`/admin/exams/${id}/publish/`, {
      method: 'POST',
    });
  },

  archiveExam: async (id: number) => {
    return apiClient<Examination>(`/admin/exams/${id}/archive/`, {
      method: 'POST',
    });
  },

  getPreview: async (id: number) => {
    return apiClient<any>(`/admin/exams/${id}/preview/`);
  },

  getAnalytics: async (id: number) => {
    return apiClient<ExamAnalyticsResponse>(`/admin/exams/${id}/analytics/`);
  },

  getResults: async (id: number, params?: ExamResultsQueryParams) => {
    return apiClient<ExamResultsResponse>(
      `/admin/exams/${id}/results/${buildQueryString(params)}`
    );
  },

  // ===== Step 3: Question Selection =====
  // All of these read from the canonical Master Question Bank and write through
  // ExaminationQuestion. Random selection runs server-side in
  // QuestionSelectionService — never in the browser.

  getAvailableQuestions: async (id: number, params?: BankQueryParams) => {
    return apiClient<PaginatedBank>(
      `/admin/exams/${id}/available-questions/${buildQueryString(params)}`
    );
  },

  getQuestionAvailability: async (id: number, params?: BankScopeParams) => {
    return apiClient<QuestionAvailability>(
      `/admin/exams/${id}/question-availability/${buildQueryString(params)}`
    );
  },

  getExamQuestions: async (id: number) => {
    return apiClient<{ results: AssignedQuestion[]; count: number; total_marks: number }>(
      `/admin/exams/${id}/questions/`
    );
  },

  addQuestions: async (id: number, question_ids: number[]) => {
    return apiClient<AddQuestionsResult>(`/admin/exams/${id}/add-questions/`, {
      method: 'POST',
      body: JSON.stringify({ question_ids }),
    });
  },

  removeQuestions: async (id: number, question_ids: number[]) => {
    return apiClient<{ removed_count: number; total_questions: number; total_marks: number }>(
      `/admin/exams/${id}/remove-questions/`,
      { method: 'POST', body: JSON.stringify({ question_ids }) }
    );
  },

  reorderQuestions: async (id: number, order_data: { question_id: number; order: number }[]) => {
    return apiClient<{ success: boolean; reordered_count: number }>(
      `/admin/exams/${id}/reorder-questions/`,
      { method: 'POST', body: JSON.stringify({ order_data }) }
    );
  },

  generateQuestions: async (id: number, payload: GenerateQuestionsPayload) => {
    return apiClient<GenerateQuestionsResult>(`/admin/exams/${id}/generate-questions/`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  // Subjective Examination management
  uploadQuestionPaper: async (id: number, file: File) => {
    const formData = new FormData();
    formData.append('pdf_file', file);
    return apiClient<{ message: string; page_count: number; file_size: number }>(
      `/admin/exams/${id}/question-paper/`,
      { method: 'POST', body: formData }
    );
  },

  deleteQuestionPaper: async (id: number) => {
    return apiClient<{ message: string }>(
      `/admin/exams/${id}/question-paper/`,
      { method: 'DELETE' }
    );
  },

  getQuestionPaperBlob: async (id: number) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api'}/admin/exams/${id}/question-paper/`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error('Failed to load question paper PDF');
    return await res.blob();
  },

  getExamSubmissions: async (examId: number, status?: string) => {
    const query = status ? `?status=${status}` : '';
    return apiClient<AdminSubjectiveSubmission[]>(`/admin/exams/${examId}/submissions/${query}`);
  },

  getAllSubjectiveSubmissions: async (params?: {
    exam_id?: number;
    status?: string;
    search?: string;
    student_id?: number;
    evaluation_status?: string;
    date_from?: string;
    date_to?: string;
  }) => {
    const qs = buildQueryString(params);
    return apiClient<AdminSubjectiveSubmission[]>(`/admin/subjective-submissions/${qs}`);
  },

  getSubjectiveSubmission: async (id: number) => {
    return apiClient<AdminSubjectiveSubmissionDetail>(`/admin/subjective-submissions/${id}/`);
  },

  getSubjectiveSubmissionByAttempt: async (attemptId: number) => {
    return apiClient<AdminSubjectiveSubmissionDetail>(`/admin/subjective-submissions/by-attempt/${attemptId}/`);
  },

  runOcr: async (submissionId: number) => {
    return apiClient<AdminSubjectiveSubmissionDetail>(`/admin/subjective-submissions/${submissionId}/ocr/`, {
      method: 'POST',
    });
  },

  updateTranscription: async (submissionId: number, extracted_text: string) => {
    return apiClient<AdminSubjectiveSubmissionDetail>(`/admin/subjective-submissions/${submissionId}/update-transcription/`, {
      method: 'POST',
      body: JSON.stringify({ extracted_text }),
    });
  },

  evaluateSubmission: async (
    submissionId: number,
    data: {
      score?: number;
      marks_obtained?: number;
      evaluator_feedback?: string;
      question_scores?: { question_number: number; marks_obtained: number; max_marks: number; feedback?: string }[];
    }
  ) => {
    return apiClient<AdminSubjectiveSubmissionDetail>(`/admin/subjective-submissions/${submissionId}/evaluate/`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  publishSubmission: async (submissionId: number) => {
    return apiClient<AdminSubjectiveSubmissionDetail>(`/admin/subjective-submissions/${submissionId}/publish/`, {
      method: 'POST',
    });
  },

  getAnswerSheetBlob: async (submissionId: number) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api'}/admin/subjective-submissions/${submissionId}/answer-sheet/`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error('Failed to load answer sheet PDF');
    return await res.blob();
  },
};

// ===== Question selection types =====

export interface BankScopeParams {
  exam?: number;
  paper?: number;
  subject?: number;
  chapter?: number;
  topic?: number;
  question_type?: string;
  tags?: string;
  /** Restrict to one QuestionCollection - "Use in Mock Exam" from Collections. */
  collection?: number;
}

export interface BankQueryParams extends BankScopeParams {
  search?: string;
  difficulty?: string;
  page?: number;
  page_size?: number;
}

export interface BankQuestion {
  id: number;
  question_id: string | null;
  text: string;
  question_type: string;
  difficulty: string;
  status: string;
  marks: number;
  subject_name: string | null;
  chapter_name: string | null;
  topic_name: string | null;
}

export interface AssignedQuestion extends BankQuestion {
  order: number;
  exam_marks: number;
}

export interface PaginatedBank {
  results: BankQuestion[];
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface QuestionAvailability {
  /** Size of the scope regardless of what this exam already holds. */
  total_in_scope: number;
  /** What remains addable, i.e. scope minus already-assigned. */
  total_available: number;
  by_difficulty: { easy: number; medium: number; hard: number };
  by_type: { mcq: number; true_false: number; subjective: number };
  selected: number;
  remaining_to_target: number;
}

export interface AddQuestionsResult {
  success: boolean;
  added_count: number;
  skipped_duplicates: number;
  not_approved_or_missing: number[];
  total_questions: number;
  total_marks: number;
}

export interface GenerateQuestionsPayload extends BankScopeParams {
  count?: number;
  difficulty_distribution?: { easy?: number; medium?: number; hard?: number };
  /** Report what would be selected without writing anything. */
  preview?: boolean;
  /** Clear the current selection first (Regenerate). */
  replace?: boolean;
}

export interface GenerateQuestionsResult {
  requested: number;
  selected: number;
  available: number;
  satisfied: boolean;
  warnings: string[];
  preview: boolean;
  questions: BankQuestion[];
  error?: string;
  total_questions?: number;
  total_marks?: number;
}
