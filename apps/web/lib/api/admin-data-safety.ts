import { apiClient } from "./client";

export interface DataSafetyOverview {
  backup_status: "healthy" | "warning" | "failed";
  last_backup: DatabaseBackup | null;
  r2_configured: boolean;
  storage_backend: string;
  retention_days: number;
  verified_backups_count: number;
  r2_verified_count: number;
  failed_backups_count: number;
  expired_backups_count: number;
  protected_backups_count: number;
  total_backups_count: number;
  trash_items_count: number;
  protected_records_count: number;
  recently_restored_count: number;
  last_permanent_delete: {
    title: string;
    item_type: string;
    deleted_by: string;
    timestamp: string;
  } | null;
  safety_warnings: string[];
}

export interface TrashItem {
  id: number;
  app_label: string;
  model_name: string;
  object_id: string;
  title: string;
  item_type: string;
  module: string;
  deleted_by: number | null;
  deleted_by_name: string;
  deleted_at: string;
  reason: string;
  details: Record<string, unknown>;
  is_restored: boolean;
  restored_at: string | null;
  restored_by_name: string | null;
  is_permanent_deleted: boolean;
  is_protected: boolean;
  protection_reason: string;
  parent_info: {
    app_label: string;
    model_name: string;
    id: string | number;
    title: string;
    is_in_trash: boolean;
  } | null;
  dependent_counts: Record<string, number>;
}

export interface DatabaseBackup {
  id: number;
  name: string;
  backup_type: "full_db" | "manual" | "scheduled" | "pre_restore" | "daily";
  status: "pending" | "in_progress" | "completed" | "verified" | "failed" | "corrupted" | "expired";
  file_path: string;
  size_bytes: number;
  checksum_sha256: string;
  is_verified: boolean;
  verified_at: string | null;
  verification_message: string;
  storage_backend: string;
  storage_key: string;
  r2_uploaded: boolean;
  r2_verified: boolean;
  r2_etag: string;
  retention_until: string | null;
  is_protected: boolean;
  completed_at: string | null;
  retry_count: number;
  restore_status: string;
  error_message: string;
  metadata: Record<string, unknown>;
  created_by_name: string;
  created_at: string;
}

export interface RecoveryStatus {
  storage_directory: string;
  pre_restore_snapshots: DatabaseBackup[];
  recovery_points: DatabaseBackup[];
  trash_recoverable_items: number;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

function toQueryString(params?: Record<string, unknown>): string {
  if (!params) return "";
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.append(key, String(value));
    }
  }
  const str = query.toString();
  return str ? `?${str}` : "";
}

export const adminDataSafetyApi = {
  getOverview: (): Promise<DataSafetyOverview> => {
    return apiClient<DataSafetyOverview>("/admin/data-safety/overview/");
  },

  getTrashItems: (params?: {
    module?: string;
    item_type?: string;
    is_protected?: boolean;
    search?: string;
    page?: number;
    ordering?: string;
  }): Promise<PaginatedResponse<TrashItem>> => {
    const qs = toQueryString(params);
    return apiClient<PaginatedResponse<TrashItem>>(`/admin/data-safety/trash/${qs}`);
  },

  restoreTrashItem: (
    id: number,
    restoreParents: boolean = false
  ): Promise<{
    success: boolean;
    message: string;
    restored_parent?: boolean;
    needs_parent_restoration?: boolean;
    parent?: { app_label: string; model_name: string; id: string | number };
  }> => {
    return apiClient(`/admin/data-safety/trash/${id}/restore/`, {
      method: "POST",
      body: JSON.stringify({ restore_parents: restoreParents }),
    });
  },

  permanentDeleteTrashItem: (
    id: number,
    confirmation: string
  ): Promise<{ success: boolean; message: string }> => {
    return apiClient(`/admin/data-safety/trash/${id}/permanent-delete/`, {
      method: "POST",
      body: JSON.stringify({ confirmation }),
    });
  },

  bulkRestoreTrashItems: (
    ids: number[],
    restoreParents: boolean = false
  ): Promise<{
    restored_count: number;
    failed_count: number;
    failed_items: Array<{ id: number; title: string; reason: string }>;
  }> => {
    return apiClient("/admin/data-safety/trash/bulk-restore/", {
      method: "POST",
      body: JSON.stringify({ ids, restore_parents: restoreParents }),
    });
  },

  getBackups: (params?: {
    status?: string;
    backup_type?: string;
    storage_backend?: string;
    is_protected?: boolean;
    r2_verified?: boolean;
    search?: string;
    page?: number;
  }): Promise<PaginatedResponse<DatabaseBackup>> => {
    const qs = toQueryString(params);
    return apiClient<PaginatedResponse<DatabaseBackup>>(`/admin/data-safety/backups/${qs}`);
  },

  createBackup: (data: {
    name?: string;
    backup_type?: string;
  }): Promise<DatabaseBackup> => {
    return apiClient<DatabaseBackup>("/admin/data-safety/backups/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  verifyBackup: (
    id: number
  ): Promise<{
    verified: boolean;
    status: string;
    message: string;
    verified_at: string | null;
    r2_verified?: boolean;
  }> => {
    return apiClient(`/admin/data-safety/backups/${id}/verify/`, {
      method: "POST",
    });
  },

  toggleProtectBackup: (
    id: number
  ): Promise<{
    success: boolean;
    is_protected: boolean;
    message: string;
    backup: DatabaseBackup;
  }> => {
    return apiClient(`/admin/data-safety/backups/${id}/toggle-protect/`, {
      method: "POST",
    });
  },

  restoreBackup: (
    id: number,
    confirmation: string
  ): Promise<{
    success: boolean;
    message: string;
    safety_backup_id?: number;
    safety_backup_name?: string;
    restored_backup_name?: string;
  }> => {
    return apiClient(`/admin/data-safety/backups/${id}/restore/`, {
      method: "POST",
      body: JSON.stringify({ confirmation }),
    });
  },

  deleteBackup: (id: number): Promise<{ success: boolean; message: string }> => {
    return apiClient(`/admin/data-safety/backups/${id}/`, {
      method: "DELETE",
    });
  },

  getRecoveryStatus: (): Promise<RecoveryStatus> => {
    return apiClient<RecoveryStatus>("/admin/data-safety/recovery/");
  },

  getBackupDownloadUrl: (id: number): string => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";
    return `${baseUrl}/admin/data-safety/backups/${id}/download/`;
  },
};
