import { apiClient, downloadFile } from './client';
import { QuestionData, PaginatedResponse } from './teacher-questions';

export interface AdminQuestion {
  id: number;
  question_id: string;
  topic_name: string;
  subject_name: string;
  position_name: string;
  question_type: string;
  status: string;
  text: string;
  options: any[];
  marks: number;
  explanation?: string;
  hint?: string;
  expected_time_minutes: number;
  usage_count: number;
  collections?: { id: number, name: string }[];
  /** Write-only: optional QuestionCollection ids to set on create/update. */
  collection_ids?: number[];
  /** Structured search/filter Tags this question carries - independent of collections. */
  tag_objects?: { id: number, name: string, slug: string, color: string, is_active: boolean }[];
  /** Write-only: optional Tag ids to set on create/update. */
  tag_ids?: number[];
  ai_status?: string;
  [key: string]: any;
}

/** Where an imported Excel/CSV file lands. Chosen in the UI, applied to every row. */
export interface ImportTarget {
  category?: number | string;
  position?: number | string;
  subject?: number | string;
  chapter?: number | string;
  topic?: number | string;
  question_type?: 'mcq' | 'true_false' | 'subjective';
  difficulty?: 'easy' | 'medium' | 'hard';
  /** Optional: add every successfully imported question to this Collection. */
  collection_id?: number;
  /** Optional: attach these Tags to every successfully imported question. */
  tag_ids?: number[];
}

export type ImportRowStatus = 'valid' | 'incomplete' | 'duplicate' | 'error';

export interface ImportRow {
  row_index: number;
  /** Spreadsheet serial number (SN column) - display only, never a database id. */
  sn?: string;
  status: ImportRowStatus;
  /** Blocking problems: the row can never be imported as-is. */
  errors: string[];
  /** Gaps the AI can fill, e.g. 'options', 'correct_answer', 'explanation'. */
  missing: string[];
  /** Set once the AI has filled this row, listing what it supplied. */
  ai_filled?: string[];
  /** Exactly what an incomplete row lacks, e.g. "Option B, D are required." */
  missing_detail?: string[];
  /** Existing Question.question_id (Q-000123) or "row N" for an in-file duplicate. */
  duplicate_of?: string | null;
  data: Record<string, string>;
}

export interface ImportReport {
  import_id: number;
  topic_id: number | null;
  question_type: string;
  difficulty: string;
  collection_id: number | null;
  tag_ids: number[];
  total_rows: number;
  valid_rows: number;
  incomplete_rows: number;
  duplicate_rows: number;
  error_rows: number;
  report_data: ImportRow[];
}

export interface QuestionStats {
  total: number;
  mcq: number;
  subjective: number;
  active: number;
  ai_pending: number;
}

export const adminQuestionApi = {
  getStats: async () => apiClient<QuestionStats>('/admin/questions/stats/'),
  getQuestions: async (params: Record<string, any> = {}) => {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value) queryParams.append(key, value.toString());
    });
    return apiClient<{ results: AdminQuestion[], next?: string, count: number }>(`/admin/questions/?${queryParams.toString()}`);
  },
  getQuestion: async (id: number) => apiClient<AdminQuestion>(`/admin/questions/${id}/`),
  createQuestion: async (data: any) => apiClient<AdminQuestion>('/admin/questions/', { method: 'POST', body: JSON.stringify(data) }),
  updateQuestion: async (id: number, data: any) => apiClient<AdminQuestion>(`/admin/questions/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteQuestion: async (id: number) => apiClient<{ detail: string }>(`/admin/questions/${id}/`, { method: 'DELETE' }),
  duplicateQuestion: async (id: number) => apiClient<{ detail: string }>(`/admin/questions/${id}/duplicate/`, { method: 'POST' }),
  // Note: the DRF @action for this is named bulk_action with no custom
  // url_path, so its real URL keeps the underscore - it does NOT become
  // bulk-action the way most routes do.
  bulkAction: async (action: string, ids: number[], collectionIds?: number[], tagIds?: number[]) => apiClient<{ error?: string, count: number }>(`/admin/questions/bulk_action/`, {
    method: 'POST',
    body: JSON.stringify({ action, ids, collection_ids: collectionIds, tag_ids: tagIds }),
  }),
  uploadCSV: async (file: File, target: ImportTarget) => {
    const formData = new FormData();
    formData.append('file', file);
    if (target.category) formData.append('category', String(target.category));
    if (target.position) formData.append('position', String(target.position));
    if (target.subject) formData.append('subject', String(target.subject));
    if (target.chapter) formData.append('chapter', String(target.chapter));
    if (target.topic) formData.append('topic', String(target.topic));
    if (target.question_type) formData.append('question_type', target.question_type);
    if (target.difficulty) formData.append('difficulty', target.difficulty);
    if (target.collection_id) formData.append('collection_id', String(target.collection_id));
    (target.tag_ids || []).forEach((id) => formData.append('tag_ids', String(id)));
    // No Content-Type header: the browser must set it so the multipart
    // boundary is included.
    return apiClient<ImportReport>('/admin/questions/import/upload/', {
      method: 'POST',
      body: formData as any,
    });
  },
  aiFillImport: async (importId: number | string) =>
    apiClient<ImportReport>(`/admin/questions/import/${importId}/ai-fill/`, { method: 'POST' }),
  commitCSV: async (importId: number | string) =>
    apiClient<{
      success: boolean;
      imported_count: number;
      question_ids?: number[];
      skipped_duplicates?: { row_index: number; existing_question_id: string; existing_id?: number }[];
      existing_question_ids?: number[];
      all_question_ids?: number[];
    }>(`/admin/questions/import/${importId}/commit/`, { method: 'POST' }),
  /** Objective question template */
  downloadTemplate: async (type: 'mcq' | 'true_false' = 'mcq') =>
    downloadFile(
      `/admin/questions/import/template/?type=${type}`,
      type === 'true_false' ? 'True-False Question Template.xlsx' : 'Objective Question Template.xlsx',
    ),
  downloadErrorReport: async (importId: number | string) =>
    downloadFile(`/admin/questions/import/${importId}/error-report/`, `import_${importId}_errors.xlsx`),
  generateOptions: async (id: number) => apiClient<any>(`/admin/questions/${id}/generate-options/`, { method: 'POST' }),
  approveOptions: async (id: number, aiOptions: any) => apiClient<any>(`/admin/questions/${id}/approve-options/`, { method: 'POST', body: JSON.stringify(aiOptions) }),
  generateBulkAIContent: async (data: any) => apiClient<any>('/admin/questions/bulk-ai-generate/', { method: 'POST', body: JSON.stringify(data) }),
  bulkCreateQuestions: async (data: any) => apiClient<any>('/admin/questions/bulk-create/', { method: 'POST', body: JSON.stringify(data) }),
};

export const getAdminReviewQueue = async (params: Record<string, any> = {}) => {
  const queryParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) queryParams.append(key, value.toString());
  });
  return apiClient<PaginatedResponse<QuestionData>>(`/admin/questions/review-queue/?${queryParams.toString()}`);
};

export const getAdminQuestion = async (id: number) => {
  return apiClient<QuestionData>(`/admin/questions/review-queue/${id}/`);
};

export const approveQuestion = async (id: number, reviewerComment?: string) => {
  return apiClient<{ detail: string }>(`/admin/questions/review-queue/${id}/approve/`, {
    method: 'POST',
    body: JSON.stringify({ reviewer_comment: reviewerComment }),
  });
};

export const rejectQuestion = async (id: number, reviewerComment: string) => {
  return apiClient<{ detail: string }>(`/admin/questions/review-queue/${id}/reject/`, {
    method: 'POST',
    body: JSON.stringify({ reviewer_comment: reviewerComment }),
  });
};

export const requestChanges = async (id: number, reviewerComment: string) => {
  return apiClient<{ detail: string }>(`/admin/questions/review-queue/${id}/request-changes/`, {
    method: 'POST',
    body: JSON.stringify({ reviewer_comment: reviewerComment }),
  });
};
