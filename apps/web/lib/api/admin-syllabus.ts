import { apiClient } from "./client";

export interface SyllabusStats {
  categories: number;
  positions: number;
  subjects: number;
  chapters: number;
  topics: number;
}

export interface AdminExamCategory {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  order: number;
  created_at: string;
  updated_at: string;
  position_count: number;
}

export interface AdminPosition {
  id: number;
  category: number | null;
  category_name: string;
  // Self-referential: null for a top-level "Level" (e.g. PSC's 5th Level),
  // set to another position's id for a "Service/Faculty" nested under it.
  parent: number | null;
  parent_name: string | null;
  name: string;
  description: string;
  is_active: boolean;
  status?: "active" | "coming_soon" | "inactive";
  order: number;
  created_at: string;
  updated_at: string;
  subject_count: number;
}

export interface AdminSubject {
  id: number;
  exam: number;
  position_name: string;
  name: string;
  code: string;
  description: string;
  is_active: boolean;
  order: number;
  created_at: string;
  updated_at: string;
  chapter_count: number;
}

export interface AdminChapter {
  id: number;
  subject: number;
  subject_name: string;
  title: string;
  description: string;
  is_active: boolean;
  order: number;
  created_at: string;
  updated_at: string;
  topic_count: number;
}

export interface AdminTopic {
  id: number;
  unit?: number;
  chapter?: number;
  chapter_name: string;
  name: string;
  description: string;
  is_active: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface ReorderItem {
  id: number;
  order: number;
}

const SYLLABUS_BASE = "/admin/syllabus";

let cachedTree: any[] | null = null;
let cachedTreePromise: Promise<any[]> | null = null;
let lastTreeFetchTime = 0;
const TREE_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

export const getAcademicTreeCached = async (forceRefresh = false): Promise<any[]> => {
  const now = Date.now();
  if (!forceRefresh && cachedTree && (now - lastTreeFetchTime < TREE_CACHE_TTL_MS)) {
    return cachedTree;
  }
  if (!forceRefresh && cachedTreePromise) {
    return cachedTreePromise;
  }
  cachedTreePromise = adminSyllabusApi.getTree()
    .then((data) => {
      cachedTree = data;
      lastTreeFetchTime = Date.now();
      cachedTreePromise = null;
      return data;
    })
    .catch((err) => {
      cachedTreePromise = null;
      throw err;
    });
  return cachedTreePromise;
};

export const clearAcademicTreeCache = () => {
  cachedTree = null;
  cachedTreePromise = null;
  lastTreeFetchTime = 0;
};

export const adminSyllabusApi = {
  // Stats
  getStats: () => apiClient<SyllabusStats>(`${SYLLABUS_BASE}/stats/`),
  
  // Tree
  getTree: () => apiClient<any[]>(`${SYLLABUS_BASE}/tree/`),
  getTreeCached: getAcademicTreeCached,
  clearTreeCache: clearAcademicTreeCache,

  // Categories
  getCategories: () => apiClient<AdminExamCategory[]>(`${SYLLABUS_BASE}/categories/`),
  getCategory: (id: number) => apiClient<AdminExamCategory>(`${SYLLABUS_BASE}/categories/${id}/`),
  createCategory: (data: Partial<AdminExamCategory>) => {
    clearAcademicTreeCache();
    return apiClient<AdminExamCategory>(`${SYLLABUS_BASE}/categories/`, { method: "POST", body: JSON.stringify(data) });
  },
  updateCategory: (id: number, data: Partial<AdminExamCategory>) => {
    clearAcademicTreeCache();
    return apiClient<AdminExamCategory>(`${SYLLABUS_BASE}/categories/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  deleteCategory: (id: number, force: boolean = true) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/categories/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" });
  },
  reorderCategories: (data: ReorderItem[]) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/categories/reorder/`, { method: "PATCH", body: JSON.stringify(data) });
  },

  // Positions.
  // A "Position / Level" in the syllabus tree is the Exam model, which lives at
  // /syllabus/exams/. Do not point these at /syllabus/positions/ — that serves
  // the standalone Position list used by the Positions admin page, and its ids
  // are not valid for the `exam` field on question sets or exams.
  getPositions: (categoryId?: number) => apiClient<AdminPosition[]>(`${SYLLABUS_BASE}/exams/${categoryId ? `?category=${categoryId}` : ''}`),
  getPosition: (id: number) => apiClient<AdminPosition>(`${SYLLABUS_BASE}/exams/${id}/`),
  createPosition: (data: Partial<AdminPosition>) => {
    clearAcademicTreeCache();
    return apiClient<AdminPosition>(`${SYLLABUS_BASE}/exams/`, { method: "POST", body: JSON.stringify(data) });
  },
  updatePosition: (id: number, data: Partial<AdminPosition>) => {
    clearAcademicTreeCache();
    return apiClient<AdminPosition>(`${SYLLABUS_BASE}/exams/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  deletePosition: (id: number, force: boolean = true) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/exams/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" });
  },
  reorderPositions: (data: ReorderItem[]) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/exams/reorder/`, { method: "PATCH", body: JSON.stringify(data) });
  },

  // Subjects
  getSubjects: (positionId?: number) => apiClient<AdminSubject[]>(`${SYLLABUS_BASE}/subjects/${positionId ? `?exam=${positionId}` : ''}`),
  getSubject: (id: number) => apiClient<AdminSubject>(`${SYLLABUS_BASE}/subjects/${id}/`),
  createSubject: (data: Partial<AdminSubject>) => {
    clearAcademicTreeCache();
    return apiClient<AdminSubject>(`${SYLLABUS_BASE}/subjects/`, { method: "POST", body: JSON.stringify(data) });
  },
  updateSubject: (id: number, data: Partial<AdminSubject>) => {
    clearAcademicTreeCache();
    return apiClient<AdminSubject>(`${SYLLABUS_BASE}/subjects/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  deleteSubject: (id: number, force: boolean = true) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/subjects/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" });
  },
  reorderSubjects: (data: ReorderItem[]) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/subjects/reorder/`, { method: "PATCH", body: JSON.stringify(data) });
  },

  // Chapters
  getChapters: (subjectId?: number) => apiClient<AdminChapter[]>(`${SYLLABUS_BASE}/chapters/${subjectId ? `?subject=${subjectId}` : ''}`),
  getChapter: (id: number) => apiClient<AdminChapter>(`${SYLLABUS_BASE}/chapters/${id}/`),
  createChapter: (data: Partial<AdminChapter>) => {
    clearAcademicTreeCache();
    return apiClient<AdminChapter>(`${SYLLABUS_BASE}/chapters/`, { method: "POST", body: JSON.stringify(data) });
  },
  updateChapter: (id: number, data: Partial<AdminChapter>) => {
    clearAcademicTreeCache();
    return apiClient<AdminChapter>(`${SYLLABUS_BASE}/chapters/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  deleteChapter: (id: number, force: boolean = true) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/chapters/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" });
  },
  reorderChapters: (data: ReorderItem[]) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/chapters/reorder/`, { method: "PATCH", body: JSON.stringify(data) });
  },

  // Topics
  getTopics: (chapterId?: number) => apiClient<AdminTopic[]>(`${SYLLABUS_BASE}/topics/${chapterId ? `?chapter=${chapterId}` : ''}`),
  getTopic: (id: number) => apiClient<AdminTopic>(`${SYLLABUS_BASE}/topics/${id}/`),
  createTopic: (data: Partial<AdminTopic>) => {
    clearAcademicTreeCache();
    return apiClient<AdminTopic>(`${SYLLABUS_BASE}/topics/`, { method: "POST", body: JSON.stringify(data) });
  },
  updateTopic: (id: number, data: Partial<AdminTopic>) => {
    clearAcademicTreeCache();
    return apiClient<AdminTopic>(`${SYLLABUS_BASE}/topics/${id}/`, { method: "PATCH", body: JSON.stringify(data) });
  },
  deleteTopic: (id: number, force: boolean = true) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/topics/${id}/${force ? '?force=true' : ''}`, { method: "DELETE" });
  },
  reorderTopics: (data: ReorderItem[]) => {
    clearAcademicTreeCache();
    return apiClient(`${SYLLABUS_BASE}/topics/reorder/`, { method: "PATCH", body: JSON.stringify(data) });
  },
};
