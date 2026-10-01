import { apiClient } from './client';

/** Examination.OBJECTIVE_CATEGORIES in exams/models.py — the four finalized
 * Objective Exam categories. May be null on older/uncategorized exams. */
export type ObjectiveCategory = "past_year" | "model" | "live" | "topicwise" | null;

export interface StudentExam {
  id: number;
  title: string;
  description: string;
  exam_type: string;
  objective_category: ObjectiveCategory;
  // Same as objective_category, except a Live Exam auto-promotes to "model"
  // 48h after its scheduled start — group listings by this, not the raw value.
  effective_category: ObjectiveCategory;
  category_name: string;
  course_id?: number | null;
  course_title?: string | null;
  exam_name: string;
  subject_name: string;
  topic_id?: number | null;
  topic_name?: string | null;
  instructions: string;
  thumbnail: string | null;
  total_questions: number;
  time_limit: number;
  total_marks: number;
  passing_marks: number;
  marks_per_question: number;
  negative_marking: boolean;
  negative_marking_value: number;
  max_attempts: number;
  allow_resume: boolean;
  start_time: string | null;
  end_time: string | null;
  status: string;
  has_attempted: boolean;
  attempts_used?: number;
  attempts_remaining?: number | null;
  active_attempt_id?: number | null;
  latest_attempt_id?: number | null;
  latest_attempt_status?: string | null;
  is_result_published?: boolean;
  requires_admin_request?: boolean;
  has_question_paper?: boolean;
  question_paper_page_count?: number;
  can_start?: boolean;
  start_blocked_reason?: string | null;
}

export interface ExaminationRequest {
  id: number;
  request_type: "exam_access" | "subjective_live";
  student: number;
  student_name: string;
  examination: number;
  examination_title: string;
  academic_exam: number | null;
  requested_exam_name: string | null;
  course: number | null;
  requested_course_title: string | null;
  subject: number | null;
  requested_subject_name: string | null;
  topic: number | null;
  requested_topic_name: string | null;
  status: "pending" | "approved" | "rejected";
  rejection_reason: string;
  reviewed_by: number | null;
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface ExpertSolution {
  id: number;
  text: string;
  question_type: string;
  option_a: string | null;
  option_b: string | null;
  option_c: string | null;
  option_d: string | null;
  correct_option: string | null;
  explanation: string;
  model_answer: string;
  marks: number;
}


export interface StudentAnswer {
  id: number;
  question: number;
  selected_option: string | null;
  answer_text?: string;
  is_correct?: boolean;
  marks_awarded?: number;
  evaluated_at?: string | null;
  question_text?: string;
  question_type?: string;
  max_marks?: number;
  option_a?: string | null;
  option_b?: string | null;
  option_c?: string | null;
  option_d?: string | null;
  correct_option?: string | null;
  explanation?: string | null;
  model_answer?: string | null;
}

export interface SubjectiveAttemptState {
  attempt_id: number;
  status: string;
  is_subjective: boolean;
  server_time: string;
  started_at: string;
  exam_expires_at: string | null;
  time_remaining_seconds: number;
  upload_expires_at: string | null;
  upload_time_remaining_seconds: number;
  can_upload: boolean;
  upload_status: string;
  has_answer_pdf: boolean;
  page_count: number;
  total_marks: number;
  pass_marks: number;
}

export interface StudentExamAttempt {
  id: number;
  examination: number;
  examination_title: string;
  started_at: string;
  submitted_at: string | null;
  status: 'in-progress' | 'upload_pending' | 'submitted' | 'evaluated' | 'completed';
  score: number;
  percentage: number;
  passed: boolean;
  time_taken_seconds: number;
  total_questions?: number;
  correct_answers?: number;
  wrong_answers?: number;
  unanswered?: number;
  needs_evaluation?: boolean;
  show_correct_answers?: boolean;
  can_review_answers?: boolean;
  answers: StudentAnswer[];
  // Subjective extensions
  is_subjective?: boolean;
  exam_expires_at?: string | null;
  upload_expires_at?: string | null;
  can_upload?: boolean;
  has_answer_pdf?: boolean;
  evaluator_feedback?: string;
  evaluator_name?: string | null;
  evaluated_at?: string | null;
  is_published?: boolean;
  published_at?: string | null;
  extracted_text?: string;
}

export interface StudentExamResult extends StudentExamAttempt {
  answers: StudentAnswer[];
  examination_exam_type?: string;
  total_marks?: number;
  needs_evaluation?: boolean;
  show_correct_answers?: boolean;
  can_review_answers?: boolean;
  evaluator_feedback?: string;
  evaluator_name?: string | null;
  evaluated_at?: string | null;
  is_published?: boolean;
  published_at?: string | null;
  has_answer_pdf?: boolean;
  has_submitted_answer_pdf?: boolean;
  subjective_submission?: {
    id: number;
    status: string;
    page_count: number;
    file_size_bytes: number;
    has_answer_pdf: boolean;
    evaluator_feedback: string;
    evaluator_name?: string | null;
    evaluated_at: string | null;
    is_published: boolean;
    published_at: string | null;
    question_scores?: {
      id?: number;
      question_number: number;
      marks_obtained: number;
      max_marks: number;
      feedback?: string;
    }[];
  };
  question_scores?: {
    id?: number;
    question_number: number;
    marks_obtained: number;
    max_marks: number;
    feedback?: string;
  }[];
}

export interface Question {
  id: number;
  text: string;
  option_a: string | null;
  option_b: string | null;
  option_c: string | null;
  option_d: string | null;
  marks: number;
  difficulty: string;
  question_type: string;
  correct_option?: string | null;
  explanation?: string | null;
  model_answer?: string | null;
}

export const OBJECTIVE_QUESTION_TYPES = ["mcq", "true_false"];
export const isSubjectiveQuestionType = (t: string) => !OBJECTIVE_QUESTION_TYPES.includes(t);

export interface AcademicHierarchyNode {
  id: number;
  name?: string;
  title?: string;
  is_active: boolean;
  exams?: AcademicHierarchyNode[];
  papers?: AcademicHierarchyNode[];
  subjects?: AcademicHierarchyNode[];
  chapters?: AcademicHierarchyNode[];
  topics?: AcademicHierarchyNode[];
}

export interface CustomExamParams {
  // Exactly one of exam_id (a specific Position/Level) or category_id (every
  // Position/Level under a Central/Provincial/Institutional bank) is
  // required - category_id builds a full-syllabus exam across all of them.
  exam_id?: number;
  category_id?: number;
  paper_id?: number;
  subject_id?: number;
  chapter_id?: number;
  topic_id?: number;
  difficulty?: string;
  question_type?: string;
  question_count?: number;
  random_questions?: boolean;
}


export const studentExamsApi = {
  getExams: async (courseId?: number) => {
    const url = courseId ? `/student/exams/?course_id=${courseId}` : '/student/exams/';
    return await apiClient<StudentExam[]>(url);
  },

  getTopicwiseTests: async (courseId?: number) => {
    const params = new URLSearchParams({ topicwise: 'true' });
    if (courseId != null) params.set('course_id', String(courseId));
    return apiClient<StudentExam[]>(`/student/exams/?${params.toString()}`);
  },
  
  getPastResults: async () => {
    // StudentExaminationAttemptViewSet sets pagination_class =
    // StandardResultsSetPagination, so this returns {count, next, previous,
    // results} - not a plain array. Unwrap defensively so a future removal
    // of pagination doesn't silently break this again either way.
    const data = await apiClient<{ results: StudentExamAttempt[] } | StudentExamAttempt[]>(
      '/student/exam-attempts/?status=submitted'
    );
    return Array.isArray(data) ? data : data.results;
  },
  
  getExamDetails: async (id: number) => {
    return await apiClient<StudentExam>(`/student/exams/${id}/`);
  },

  getExamRequests: () => apiClient<ExaminationRequest[]>("/student/exam-requests/"),

  requestSubjectiveExam: (payload: {
    academic_exam: number;
    course?: number;
    subject?: number;
    topic?: number;
  }) => apiClient<ExaminationRequest>("/student/exam-requests/", {
    method: "POST",
    body: JSON.stringify({ request_type: "subjective_live", ...payload }),
  }),

  requestExamAccess: (examinationId: number) => apiClient<ExaminationRequest>("/student/exam-requests/", {
    method: "POST",
    body: JSON.stringify({ examination: examinationId }),
  }),

  getExpertSolution: (examinationId: number) => apiClient<{
    examination: number;
    title: string;
    solutions: ExpertSolution[];
  }>(`/student/exams/${examinationId}/expert-solution/`),
  
  generateCustomExam: async (params: CustomExamParams) => {
    return await apiClient<StudentExamAttempt>('/student/exams/generate_custom/', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },
  
  startExam: async (id: number) => {
    return await apiClient<StudentExamAttempt>(`/student/exams/${id}/start/`, {
      method: 'POST'
    });
  },
  
  getAttempt: async (attemptId: number) => {
    return await apiClient<StudentExamAttempt>(`/student/exam-attempts/${attemptId}/`);
  },
  
  getAttemptQuestions: async (attemptId: number) => {
    return await apiClient<Question[]>(`/student/exam-attempts/${attemptId}/questions/`);
  },
  


  getAcademicHierarchy: async (courseId?: number) => {
    const url = courseId ? `/student/exams/academic-hierarchy/?course_id=${courseId}` : '/student/exams/academic-hierarchy/';
    return await apiClient<AcademicHierarchyNode[]>(url);
  },

  getAvailableQuestionCount: async (params: Partial<CustomExamParams>) => {
    const res = await apiClient<{available: number}>('/student/exams/available-questions/', {
      method: 'POST',
      body: JSON.stringify(params)
    });
    return res.available;
  },
  
  saveAnswer: async (attemptId: number, questionId: number, selectedOption: string | null) => {
    return await apiClient(`/student/exam-attempts/${attemptId}/answer/`, {
      method: 'POST',
      body: JSON.stringify({
        question: questionId,
        selected_option: selectedOption
      })
    });
  },

  saveAnswerText: async (attemptId: number, questionId: number, answerText: string) => {
    return await apiClient(`/student/exam-attempts/${attemptId}/answer/`, {
      method: 'POST',
      body: JSON.stringify({
        question: questionId,
        answer_text: answerText,
      })
    });
  },
  
  submitAttempt: async (attemptId: number) => {
    return await apiClient(`/student/exam-attempts/${attemptId}/submit/`, {
      method: 'POST'
    });
  },
  
  getResult: async (attemptId: number) => {
    return await apiClient<StudentExamResult>(`/student/exam-attempts/${attemptId}/result/`);
  },

  // Subjective Examination methods
  getAttemptState: async (attemptId: number) => {
    return await apiClient<SubjectiveAttemptState>(`/student/exam-attempts/${attemptId}/state/`);
  },

  getQuestionPaperBlob: async (examId: number) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api'}/student/exams/${examId}/question-paper/`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error('Failed to load question paper PDF');
    return await res.blob();
  },

  uploadAnswerSheet: async (attemptId: number, formData: FormData) => {
    return await apiClient<{
      message: string;
      page_count: number;
      file_size_bytes: number;
      status: string;
      can_upload: boolean;
    }>(`/student/exam-attempts/${attemptId}/answer-sheet/`, {
      method: 'POST',
      body: formData,
    });
  },

  getAnswerSheetBlob: async (attemptId: number) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api'}/student/exam-attempts/${attemptId}/answer-sheet/`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error('Failed to load submitted answer sheet');
    return await res.blob();
  },
};

