import { apiClient } from "./client";

export interface OfficialExamSchedule {
  id: number;
  title: string;
  exam_type?: "all" | "topicwise" | "objective" | "subjective";
  exam_category: number | null;
  category_name?: string | null;
  exam: number | null;
  exam_name?: string | null;
  description: string;
  exam_date: string; // YYYY-MM-DD
  exam_time: string | null; // HH:MM:SS
  exam_datetime: string | null; // ISO string
  timezone: string;
  application_deadline: string | null;
  result_expected_date: string | null;
  official_notice_url: string;
  is_published?: boolean;
  is_active?: boolean;
  is_upcoming?: boolean;
  created_at?: string;
  updated_at?: string;
  server_time?: string;
}

export interface OfficialExamScheduleNextResponse {
  schedule: OfficialExamSchedule | null;
  message?: string;
  server_time: string;
}

export interface UpcomingMockExam {
  id: number;
  title: string;
  description: string;
  exam_type: string;
  category_name: string | null;
  exam_name: string | null;
  start_time: string | null; // ISO string
  end_time: string | null; // ISO string
  duration_minutes: number;
  total_questions: number;
  total_marks: number;
  status: "UPCOMING" | "LIVE" | "COMPLETED" | "DRAFT";
  can_start: boolean;
  active_attempt_id?: number | null;
  has_attempted?: boolean;
  server_time: string;
}

export interface UpcomingMockExamResponse {
  mock_exam: UpcomingMockExam | null;
  status: "UPCOMING" | "LIVE" | "COMPLETED" | "NONE";
  message?: string;
  server_time: string;
}

export const schedulesApi = {
  // Student Public Endpoints
  getNextOfficialExam: async (courseId?: number): Promise<OfficialExamScheduleNextResponse> => {
    const url = courseId ? `/schedules/next/?course_id=${courseId}` : "/schedules/next/";
    return apiClient<OfficialExamScheduleNextResponse>(url, { skipRedirect: true });
  },

  getUpcomingMockExam: async (): Promise<UpcomingMockExamResponse> => {
    return apiClient<UpcomingMockExamResponse>("/student/mock-exams/upcoming/");
  },

  // Admin Endpoints
  getAdminSchedules: async (params?: {
    search?: string;
    is_published?: boolean;
    is_active?: boolean;
    exam_type?: string;
  }): Promise<OfficialExamSchedule[]> => {
    const query = new URLSearchParams();
    if (params?.search) query.append("search", params.search);
    if (params?.is_published !== undefined) query.append("is_published", String(params.is_published));
    if (params?.is_active !== undefined) query.append("is_active", String(params.is_active));
    if (params?.exam_type && params.exam_type !== "all") query.append("exam_type", params.exam_type);
    const queryString = query.toString();
    const url = queryString ? `/admin/schedules/?${queryString}` : "/admin/schedules/";
    const res = await apiClient<any>(url);
    if (Array.isArray(res)) return res;
    if (res && Array.isArray(res.results)) return res.results;
    return [];
  },


  createSchedule: async (data: Partial<OfficialExamSchedule>): Promise<OfficialExamSchedule> => {
    return apiClient<OfficialExamSchedule>("/admin/schedules/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  updateSchedule: async (id: number, data: Partial<OfficialExamSchedule>): Promise<OfficialExamSchedule> => {
    return apiClient<OfficialExamSchedule>(`/admin/schedules/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  deleteSchedule: async (id: number): Promise<{ success?: boolean }> => {
    return apiClient<{ success?: boolean }>(`/admin/schedules/${id}/`, {
      method: "DELETE",
    });
  },

  setActiveSchedule: async (id: number): Promise<OfficialExamSchedule> => {
    return apiClient<OfficialExamSchedule>(`/admin/schedules/${id}/set-active/`, {
      method: "POST",
    });
  },

  togglePublishSchedule: async (id: number): Promise<OfficialExamSchedule> => {
    return apiClient<OfficialExamSchedule>(`/admin/schedules/${id}/toggle-publish/`, {
      method: "POST",
    });
  },
};
