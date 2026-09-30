import { apiClient } from "./client";

export interface ApiExamCategory {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  order: number;
  position_count: number;
}

export type ExamStatus = "active" | "coming_soon" | "inactive";

export interface ApiExam {
  id: number;
  category: number;
  category_name: string;
  // Self-referential: null for a top-level "Level" (e.g. PSC's 5th Level),
  // set to another exam's id for a "Preparation/Service" nested under it.
  parent?: number | null;
  name: string;
  description: string;
  status: ExamStatus;
  is_active: boolean;
  order: number;
  paper_count: number;
}

export interface ApiPaper {
  id: number;
  exam: number;
  exam_name: string;
  name: string;
  paper_number: string;
  description: string;
  is_active: boolean;
  order: number;
  subject_count: number;
}

export interface ApiSubject {
  id: number;
  paper: number;
  paper_name?: string;
  exam?: number;
  name: string;
  code: string;
  description: string;
  is_active: boolean;
  order: number;
  chapter_count: number;
  notes_count?: number;
  questions_count?: number;
  exams_count?: number;
}

export interface ApiChapter {
  id: number;
  subject: number;
  subject_name?: string;
  title: string;
  name?: string;
  description: string;
  is_active: boolean;
  order: number;
  topic_count: number;
  notes_count?: number;
  questions_count?: number;
  exams_count?: number;
}

export interface ApiTopic {
  id: number;
  chapter: number;
  chapter_name?: string;
  name: string;
  description: string;
  is_active: boolean;
  order: number;
  notes_count?: number;
  questions_count?: number;
  exams_count?: number;
}

export interface NodeDependenciesResponse {
  model: string;
  id: number;
  name: string;
  has_dependencies: boolean;
  counts: {
    notes: number;
    questions: number;
    exams: number;
    children: number;
  };
  message: string;
  is_active: boolean;
}

export const adminAcademicApi = {
  // Stats & Tree
  getStats: () => apiClient<any>("/admin/syllabus/stats/"),
  getTree: () => apiClient<any>("/admin/syllabus/tree/"),
  getAcademicTree: (examId: number) => apiClient<any[]>(`/admin/study-materials/academic-tree/?exam_id=${examId}`),
  
  // Reorder
  reorderItems: (endpoint: string, items: {id: number, order: number}[]) => 
    apiClient<any>(`/admin/academic/${endpoint}/reorder/`, {
      method: "PATCH",
      body: JSON.stringify(items)
    }),

  // Dependencies check for safe deletion
  getNodeDependencies: (model: "subjects" | "chapters" | "topics" | "exams", id: number) =>
    apiClient<NodeDependenciesResponse>(`/admin/academic/${model}/${id}/dependencies/`),

  // Archive / toggle active status
  archiveNode: (model: "subjects" | "chapters" | "topics" | "exams", id: number, isActive?: boolean) =>
    apiClient<{ id: number; is_active: boolean; status: string; message: string }>(
      `/admin/academic/${model}/${id}/archive/`,
      {
        method: "PATCH",
        body: JSON.stringify(isActive !== undefined ? { is_active: isActive } : {})
      }
    ),

  // Delete node with optional force query param
  deleteNode: (model: "subjects" | "chapters" | "topics" | "exams", id: number, force: boolean = true) =>
    apiClient<any>(`/admin/academic/${model}/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" }),

  // Exam Categories
  getCategories: () => apiClient<ApiExamCategory[]>("/admin/academic/categories/"),
  
  // Exams
  getExams: (categoryId?: number) =>
    apiClient<ApiExam[]>(`/admin/academic/exams/${categoryId ? `?category=${categoryId}` : ''}`),
  getExam: (id: number) => apiClient<ApiExam>(`/admin/academic/exams/${id}/`),
  createExam: (data: Partial<ApiExam>) => apiClient<ApiExam>(`/admin/academic/exams/`, { method: "POST", body: JSON.stringify(data) }),
  updateExam: (id: number, data: Partial<ApiExam>) => apiClient<ApiExam>(`/admin/academic/exams/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteExam: (id: number, force: boolean = true) => apiClient(`/admin/academic/exams/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" }),

  // Papers
  getPapers: (examId?: number) =>
    apiClient<ApiPaper[]>(`/admin/academic/papers/${examId ? `?exam=${examId}` : ''}`),
  getPaper: (id: number) => apiClient<ApiPaper>(`/admin/academic/papers/${id}/`),
  createPaper: (data: Partial<ApiPaper>) => apiClient<ApiPaper>(`/admin/academic/papers/`, { method: "POST", body: JSON.stringify(data) }),
  updatePaper: (id: number, data: Partial<ApiPaper>) => apiClient<ApiPaper>(`/admin/academic/papers/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  deletePaper: (id: number, force: boolean = true) => apiClient(`/admin/academic/papers/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" }),

  // Subjects
  getSubjects: (paperId?: number) =>
    apiClient<ApiSubject[]>(`/admin/academic/subjects/${paperId ? `?paper=${paperId}` : ''}`),
  getSubject: (id: number) => apiClient<ApiSubject>(`/admin/academic/subjects/${id}/`),
  createSubject: (data: Partial<ApiSubject>) => apiClient<ApiSubject>(`/admin/academic/subjects/`, { method: "POST", body: JSON.stringify(data) }),
  updateSubject: (id: number, data: Partial<ApiSubject>) => apiClient<ApiSubject>(`/admin/academic/subjects/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteSubject: (id: number, force: boolean = true) => apiClient(`/admin/academic/subjects/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" }),
  reorderSubjects: (data: { id: number; order: number }[]) => apiClient(`/admin/academic/subjects/reorder/`, { method: "PATCH", body: JSON.stringify(data) }),

  // Chapters
  getChapters: (subjectId?: number) =>
    apiClient<ApiChapter[]>(`/admin/academic/chapters/${subjectId ? `?subject=${subjectId}` : ''}`),
  getChapter: (id: number) => apiClient<ApiChapter>(`/admin/academic/chapters/${id}/`),
  createChapter: (data: Partial<ApiChapter>) => apiClient<ApiChapter>(`/admin/academic/chapters/`, { method: "POST", body: JSON.stringify(data) }),
  updateChapter: (id: number, data: Partial<ApiChapter>) => apiClient<ApiChapter>(`/admin/academic/chapters/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteChapter: (id: number, force: boolean = true) => apiClient(`/admin/academic/chapters/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" }),

  // Topics
  getTopics: (chapterId?: number) =>
    apiClient<ApiTopic[]>(`/admin/academic/topics/${chapterId ? `?chapter=${chapterId}` : ''}`),
  getTopic: (id: number) => apiClient<ApiTopic>(`/admin/academic/topics/${id}/`),
  createTopic: (data: Partial<ApiTopic>) => apiClient<ApiTopic>(`/admin/academic/topics/`, { method: "POST", body: JSON.stringify(data) }),
  updateTopic: (id: number, data: Partial<ApiTopic>) => apiClient<ApiTopic>(`/admin/academic/topics/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteTopic: (id: number, force: boolean = true) => apiClient(`/admin/academic/topics/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" }),
};
