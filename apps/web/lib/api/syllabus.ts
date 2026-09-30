import { apiClient } from "./client";
import { StudyMaterial } from "./notes";

export type TopicStatus = "completed" | "in-progress" | "not-started";

export interface TopicContentResponse {
  id: number;
  name: string;
  description: string;
  materials: StudyMaterial[];
}

export interface Topic {
  id: number;
  name: string;
  status: TopicStatus;
  progress: number;
  accuracy: number | null;
  description?: string;
}

export interface Unit {
  id: number;
  title: string;
  topics: Topic[];
}

export interface Subject {
  id: number;
  name: string;
  code: string;
  progress: number;
  description: string;
  units: Unit[];
}

export interface Exam {
  id: number;
  title: string;
  // The name to show in pickers: `title`, qualified with the exam's real
  // parent level / category only when two listed exams share a title.
  display_name?: string;
  description: string;
  subjects: Subject[];
}

export const syllabusApi = {
  getExams: async (courseId?: number | null): Promise<Exam[]> => {
    const query = courseId == null ? "" : `?course_id=${courseId}`;
    return apiClient<Exam[]>(`/exams/${query}`);
  },
  
  getExam: async (id: number): Promise<Exam> => {
    return apiClient<Exam>(`/exams/${id}/`);
  },

  updateTopicProgress: async (topicId: number, status: TopicStatus) => {
    return apiClient(`/topic-progress/`, {
      method: "POST",
      body: JSON.stringify({
        topic: topicId,
        status,
        progress: status === "completed" ? 100 : status === "in-progress" ? 50 : 0
      }),
    });
  },

  getTopicContent: async (topicId: number): Promise<TopicContentResponse> => {
    return apiClient<TopicContentResponse>(`/topics/${topicId}/content/`);
  }
};
