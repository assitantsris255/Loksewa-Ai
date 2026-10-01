import { apiClient } from './client';

export interface SubjectiveQuestionSet {
  id: number;
  title: string;
  description?: string;
  pdf_file: string;
  file_name?: string;
  file_size?: number;
  exam_category: number;
  category_id?: number;
  category_name?: string;
  level: number;
  level_id?: number;
  level_name?: string;
  course?: number | null;
  course_name?: string;
  subject?: number | null;
  subject_name?: string;
  duration_minutes: number;
  total_marks: number;
  question_count: number;
  status: 'active' | 'inactive' | 'archived';
  created_by?: number;
  created_by_name?: string;
  created_at: string;
  updated_at: string;
  usage_count: number;
  last_used_at?: string | null;
}

export interface SubjectiveSetFilterParams {
  search?: string;
  exam_category?: number | string;
  level?: number | string;
  subject?: number | string;
  status?: string;
  ordering?: string;
  page?: number;
}

export const adminSubjectiveSetsApi = {
  getSets: async (params: SubjectiveSetFilterParams = {}) => {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        queryParams.append(key, value.toString());
      }
    });
    const qs = queryParams.toString();
    return apiClient<{ results: SubjectiveQuestionSet[]; next?: string; previous?: string; count: number } | SubjectiveQuestionSet[]>(
      `/admin/subjective-question-sets/${qs ? `?${qs}` : ''}`
    );
  },

  getSet: async (id: number) => {
    return apiClient<SubjectiveQuestionSet>(`/admin/subjective-question-sets/${id}/`);
  },

  createSet: async (data: FormData) => {
    return apiClient<SubjectiveQuestionSet>('/admin/subjective-question-sets/', {
      method: 'POST',
      body: data as any,
    });
  },

  updateSet: async (id: number, data: FormData | Partial<SubjectiveQuestionSet>) => {
    const isFormData = data instanceof FormData;
    return apiClient<SubjectiveQuestionSet>(`/admin/subjective-question-sets/${id}/`, {
      method: 'PATCH',
      body: isFormData ? (data as any) : JSON.stringify(data),
      ...(isFormData ? {} : { headers: { 'Content-Type': 'application/json' } }),
    });
  },

  archiveSet: async (id: number) => {
    return apiClient<SubjectiveQuestionSet>(`/admin/subjective-question-sets/${id}/archive/`, {
      method: 'POST',
    });
  },

  activateSet: async (id: number) => {
    return apiClient<SubjectiveQuestionSet>(`/admin/subjective-question-sets/${id}/activate/`, {
      method: 'POST',
    });
  },

  deleteSet: async (id: number) => {
    return apiClient<{ detail?: string }>(`/admin/subjective-question-sets/${id}/`, {
      method: 'DELETE',
    });
  },
};
