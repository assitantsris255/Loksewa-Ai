"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  HardDrive,
  CheckCircle2,
  AlertTriangle,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  ShieldAlert,
  RotateCcw,
  Plus,
  Trash2,
  FileCheck,
  X,
  Copy,
  RefreshCw,
  Cloud,
  Shield,
  Eye,
  Lock,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import toast from "react-hot-toast";
import {
  adminDataSafetyApi,
  DatabaseBackup,
} from "@/lib/api/admin-data-safety";

export default function AdminDatabaseBackupsPage() {
  const [backups, setBackups] = useState<DatabaseBackup[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [storageFilter, setStorageFilter] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newBackupName, setNewBackupName] = useState("");
  const [newBackupType, setNewBackupType] = useState("manual");
  const [isCreating, setIsCreating] = useState(false);

  // Details Modal
  const [selectedBackupForDetails, setSelectedBackupForDetails] = useState<DatabaseBackup | null>(null);

  // Restore Modal
  const [selectedBackupForRestore, setSelectedBackupForRestore] = useState<DatabaseBackup | null>(null);
  const [restoreConfirmText, setRestoreConfirmText] = useState("");
  const [isRestoring, setIsRestoring] = useState(false);

  const fetchBackups = async () => {
    try {
      setIsLoading(true);
      const params: Record<string, unknown> = { page };
      if (statusFilter) params.status = statusFilter;
      if (typeFilter) params.backup_type = typeFilter;
      if (storageFilter) params.storage_backend = storageFilter;

      const res = await adminDataSafetyApi.getBackups(params);
      setBackups(res.results || []);
      setTotalCount(res.count || 0);
    } catch (err: unknown) {
      console.error("Failed to load backups:", err);
      const msg = err instanceof Error ? err.message : "Failed to load database backups.";
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchBackups();
  }, [page, statusFilter, typeFilter, storageFilter]);

  const handleCreateBackup = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsCreating(true);
      toast.loading("Generating database archive and streaming to Cloudflare R2...", { id: "backup-create" });
      const b = await adminDataSafetyApi.createBackup({
        name: newBackupName.trim() || undefined,
        backup_type: newBackupType,
      });
      toast.success(`Backup "${b.name}" created and verified successfully!`, { id: "backup-create" });
      setShowCreateModal(false);
      setNewBackupName("");
      fetchBackups();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create backup archive.";
      toast.error(msg, { id: "backup-create" });
    } finally {
      setIsCreating(false);
    }
  };

  const handleVerify = async (backup: DatabaseBackup) => {
    try {
      toast.loading(`Verifying integrity & R2 object for "${backup.name}"...`, { id: `verify-${backup.id}` });
      const res = await adminDataSafetyApi.verifyBackup(backup.id);
      if (res.verified) {
        toast.success(`Verified: ${res.message}`, { id: `verify-${backup.id}` });
      } else {
        toast.error(`Verification Failed: ${res.message}`, { id: `verify-${backup.id}` });
      }
      fetchBackups();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Verification request failed.";
      toast.error(msg, { id: `verify-${backup.id}` });
    }
  };

  const handleToggleProtect = async (backup: DatabaseBackup) => {
    try {
      toast.loading(backup.is_protected ? "Removing retention protection shield..." : "Activating retention protection shield...", { id: `protect-${backup.id}` });
      const res = await adminDataSafetyApi.toggleProtectBackup(backup.id);
      toast.success(res.message, { id: `protect-${backup.id}` });
      if (selectedBackupForDetails && selectedBackupForDetails.id === backup.id) {
        setSelectedBackupForDetails(res.backup);
      }
      fetchBackups();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to toggle backup protection.";
      toast.error(msg, { id: `protect-${backup.id}` });
    }
  };

  const handleRestore = async () => {
    if (!selectedBackupForRestore) return;

    if (restoreConfirmText !== "RESTORE DATABASE") {
      toast.error("Please type RESTORE DATABASE exactly to confirm.");
      return;
    }

    try {
      setIsRestoring(true);
      toast.loading("Creating safety snapshot and restoring database...", { id: "restore-db" });
      const res = await adminDataSafetyApi.restoreBackup(
        selectedBackupForRestore.id,
        restoreConfirmText
      );
      toast.success(res.message || "Database restoration completed successfully!", { id: "restore-db" });
      setSelectedBackupForRestore(null);
      setRestoreConfirmText("");
      fetchBackups();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Restoration failed.";
      toast.error(msg, { id: "restore-db" });
    } finally {
      setIsRestoring(false);
    }
  };

  const handleDelete = async (backup: DatabaseBackup) => {
    if (backup.is_protected) {
      toast.error("This backup is protected from deletion. Remove the protection shield first.");
      return;
    }
    if (!confirm(`Are you sure you want to delete backup archive "${backup.name}"? This removes both the local file and Cloudflare R2 off-site copy.`)) return;
    try {
      toast.loading("Deleting backup from local & off-site storage...", { id: `del-${backup.id}` });
      await adminDataSafetyApi.deleteBackup(backup.id);
      toast.success("Backup deleted successfully.", { id: `del-${backup.id}` });
      if (selectedBackupForDetails?.id === backup.id) {
        setSelectedBackupForDetails(null);
      }
      fetchBackups();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete backup.";
      toast.error(msg, { id: `del-${backup.id}` });
    }
  };

  const copyChecksum = (checksum: string) => {
    navigator.clipboard.writeText(checksum);
    toast.success("SHA-256 Checksum copied to clipboard!");
  };

  const formatBytes = (bytes: number) => {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link
              href="/admin-dashboard/data-safety"
              className="text-slate-500 hover:text-slate-800 text-sm flex items-center gap-1"
            >
              <ArrowLeft className="h-4 w-4" />
              Data Safety Overview
            </Link>
          </div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Database Backups & Cloudflare R2 Off-Site
            </h1>
            <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
              {totalCount} Backups
            </Badge>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Dual-layer database snapshots (.json.gz) with Cloudflare R2 off-site replication and SHA-256 integrity verification.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchBackups()}
            disabled={isLoading}
            className="gap-1.5"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={() => setShowCreateModal(true)}
            className="gap-1.5 bg-slate-900 hover:bg-slate-800 text-white"
          >
            <Plus className="h-4 w-4" />
            Create Backup
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={typeFilter}
          onChange={(e) => {
            setTypeFilter(e.target.value);
            setPage(1);
          }}
          className="h-9 px-3 rounded-md border text-xs bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200"
        >
          <option value="">All Backup Types</option>
          <option value="daily">Daily Automatic</option>
          <option value="manual">Manual Admin Backups</option>
          <option value="pre_restore">Pre-Restore Safety Snapshots</option>
          <option value="full">Full Database Backups</option>
          <option value="scheduled">Scheduled Routine</option>
        </select>

        <select
          value={storageFilter}
          onChange={(e) => {
            setStorageFilter(e.target.value);
            setPage(1);
          }}
          className="h-9 px-3 rounded-md border text-xs bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200"
        >
          <option value="">All Storage Locations</option>
          <option value="r2">Cloudflare R2 (Off-Site)</option>
          <option value="local">Local Filesystem Only</option>
        </select>

        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="h-9 px-3 rounded-md border text-xs bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200"
        >
          <option value="">All Verification States</option>
          <option value="verified">Verified (Passed)</option>
          <option value="failed">Failed Verification</option>
          <option value="expired">Expired / Cleaned Up</option>
          <option value="in_progress">In Progress</option>
        </select>
      </div>

      {/* Backups Table */}
      <Card className="border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-600 dark:text-slate-400 font-semibold border-b">
              <tr>
                <th className="p-3.5">Backup Name & Key</th>
                <th className="p-3.5">Type</th>
                <th className="p-3.5">Storage</th>
                <th className="p-3.5">Verification</th>
                <th className="p-3.5">Shield</th>
                <th className="p-3.5">Size</th>
                <th className="p-3.5">SHA-256 Checksum</th>
                <th className="p-3.5">Created Date</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {isLoading ? (
                <tr>
                  <td colSpan={9} className="p-8 text-center text-slate-500">
                    Loading database backup records...
                  </td>
                </tr>
              ) : backups.length === 0 ? (
                <tr>
                  <td colSpan={9} className="p-12 text-center text-slate-500">
                    <HardDrive className="h-8 w-8 mx-auto text-slate-400 mb-2 opacity-50" />
                    <p className="font-medium text-slate-700 dark:text-slate-300">No database backups found</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Click &ldquo;Create Backup&rdquo; to generate a verified, compressed snapshot.
                    </p>
                  </td>
                </tr>
              ) : (
                backups.map((b) => (
                  <tr
                    key={b.id}
                    className="hover:bg-slate-50/70 dark:hover:bg-slate-900/40 transition-colors"
                  >
                    <td className="p-3.5">
                      <div className="font-medium text-slate-900 dark:text-white flex items-center gap-2">
                        <span>{b.name}</span>
                        {b.is_protected && (
                          <Badge variant="outline" className="text-[10px] bg-purple-50 text-purple-700 border-purple-200">
                            Protected
                          </Badge>
                        )}
                      </div>
                      <div className="text-xs text-slate-400 font-mono mt-0.5 truncate max-w-xs" title={b.storage_key || b.file_path}>
                        {b.storage_key ? b.storage_key.split("/").slice(-1)[0] : (b.file_path ? b.file_path.split(/[\\/]/).pop() : "archive.json.gz")}
                      </div>
                    </td>

                    <td className="p-3.5">
                      <Badge variant="outline" className="text-xs capitalize">
                        {b.backup_type.replace(/_/g, " ")}
                      </Badge>
                    </td>

                    <td className="p-3.5">
                      <div className="flex flex-col gap-1 items-start">
                        {b.storage_backend === "r2" ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-950/40 px-2 py-0.5 rounded border border-sky-200 dark:border-sky-800">
                            <Cloud className="h-3 w-3" />
                            Cloudflare R2
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                            <HardDrive className="h-3 w-3" />
                            Local Only
                          </span>
                        )}
                        {b.r2_verified && (
                          <span className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400 flex items-center gap-0.5">
                            <CheckCircle2 className="h-2.5 w-2.5" /> R2 Verified
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="p-3.5">
                      {b.status === "verified" ? (
                        <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                          <span>Verified</span>
                        </div>
                      ) : b.status === "failed" || b.status === "corrupted" ? (
                        <div className="flex items-center gap-1.5 text-rose-600 dark:text-rose-400 text-xs font-medium">
                          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                          <span>{b.status}</span>
                        </div>
                      ) : b.status === "expired" ? (
                        <Badge variant="secondary" className="text-xs bg-slate-100 text-slate-500">
                          Expired
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-xs capitalize">
                          {b.status}
                        </Badge>
                      )}
                    </td>

                    <td className="p-3.5">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleProtect(b)}
                        className={`h-7 px-2 text-xs gap-1 ${
                          b.is_protected
                            ? "text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200"
                            : "text-slate-400 hover:text-purple-600"
                        }`}
                        title={b.is_protected ? "Protected from automated retention pruning. Click to unprotect." : "Click to shield this backup from deletion."}
                      >
                        <Shield className={`h-3.5 w-3.5 ${b.is_protected ? "fill-purple-600 text-purple-600" : ""}`} />
                        <span>{b.is_protected ? "Shielded" : "Shield"}</span>
                      </Button>
                    </td>

                    <td className="p-3.5 text-xs text-slate-600 dark:text-slate-300 font-mono">
                      {formatBytes(b.size_bytes)}
                    </td>

                    <td className="p-3.5 text-xs">
                      {b.checksum_sha256 ? (
                        <div className="flex items-center gap-1 text-slate-500 font-mono text-[11px]">
                          <span>{b.checksum_sha256.substring(0, 10)}...</span>
                          <button
                            onClick={() => copyChecksum(b.checksum_sha256)}
                            className="p-1 hover:text-slate-800 text-slate-400"
                            title="Copy full checksum"
                          >
                            <Copy className="h-3 w-3" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-slate-400 italic">Pending</span>
                      )}
                    </td>

                    <td className="p-3.5 text-xs text-slate-500">
                      <div>
                        {new Date(b.created_at).toLocaleString([], {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </div>
                      <div className="text-[11px] text-slate-400">by {b.created_by_name || "System"}</div>
                    </td>

                    <td className="p-3.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setSelectedBackupForDetails(b)}
                          className="text-xs h-7 px-2 text-slate-600 hover:text-slate-900"
                          title="View Backup Details & Metadata"
                        >
                          <Eye className="h-3.5 w-3.5" />
                        </Button>

                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleVerify(b)}
                          className="text-xs h-7 px-2.5 gap-1 border-slate-300 text-slate-700 hover:bg-slate-100"
                          title="Verify SHA-256 archive checksum & R2 object"
                        >
                          <FileCheck className="h-3.5 w-3.5" />
                          Verify
                        </Button>

                        <a
                          href={adminDataSafetyApi.getBackupDownloadUrl(b.id)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-xs h-7 px-2 text-slate-600 hover:text-slate-900"
                            title="Download GZIP Archive (Super Admin)"
                          >
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                        </a>

                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setSelectedBackupForRestore(b);
                            setRestoreConfirmText("");
                          }}
                          className="text-xs h-7 px-2.5 gap-1 border-amber-300 text-amber-800 hover:bg-amber-50"
                          title="Restore live database from this backup"
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                          Restore
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDelete(b)}
                          disabled={b.is_protected}
                          className={`text-xs h-7 px-2 ${
                            b.is_protected ? "text-slate-300 cursor-not-allowed" : "text-rose-500 hover:text-rose-700 hover:bg-rose-50"
                          }`}
                          title={b.is_protected ? "Backup is protected from deletion" : "Delete Backup Archive"}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalCount > pageSize && (
          <div className="p-4 border-t flex items-center justify-between text-xs text-slate-500">
            <div>
              Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, totalCount)} of{" "}
              {totalCount} records
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
                className="h-7 px-2"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="px-2 font-medium">Page {page}</span>
              <Button
                variant="outline"
                size="sm"
                disabled={page * pageSize >= totalCount}
                onClick={() => setPage(page + 1)}
                className="h-7 px-2"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Modal 1: Create Backup */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border rounded-xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <HardDrive className="h-5 w-5 text-slate-700 dark:text-slate-200" />
                <h3 className="font-semibold text-base text-slate-900 dark:text-white">
                  Create Database Backup
                </h3>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowCreateModal(false)}
                className="h-7 w-7 p-0"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <form onSubmit={handleCreateBackup} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Backup Label / Name (Optional)
                </label>
                <Input
                  placeholder="e.g., Pre-Exam Deployment Backup"
                  value={newBackupName}
                  onChange={(e) => setNewBackupName(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Backup Type
                </label>
                <select
                  value={newBackupType}
                  onChange={(e) => setNewBackupType(e.target.value)}
                  className="w-full h-9 px-3 rounded-md border text-sm bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800"
                >
                  <option value="manual">Manual Admin Backup</option>
                  <option value="daily">Daily Scheduled Backup</option>
                  <option value="full">Full Database Snapshot</option>
                  <option value="scheduled">Scheduled Routine</option>
                </select>
              </div>

              <p className="text-xs text-slate-500">
                The system packages all relational tables into a compressed .json.gz archive, computes a SHA-256 hash, and replicates it to Cloudflare R2 off-site storage.
              </p>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isCreating}
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={isCreating}
                  className="bg-slate-900 hover:bg-slate-800 text-white"
                >
                  {isCreating ? "Generating Archive..." : "Start Backup"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal 2: Details Modal */}
      {selectedBackupForDetails && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border rounded-xl max-w-xl w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <HardDrive className="h-5 w-5 text-slate-700 dark:text-slate-200" />
                <h3 className="font-semibold text-base text-slate-900 dark:text-white">
                  Backup Details & Cryptographic Audit
                </h3>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedBackupForDetails(null)}
                className="h-7 w-7 p-0"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg space-y-2 border">
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Backup Name:</span>
                  <span className="font-bold text-slate-900 dark:text-white">{selectedBackupForDetails.name}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Backup ID:</span>
                  <span className="font-mono text-slate-700 dark:text-slate-300">#{selectedBackupForDetails.id}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Backup Type:</span>
                  <Badge variant="outline" className="capitalize">{selectedBackupForDetails.backup_type.replace(/_/g, " ")}</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Status:</span>
                  <Badge variant="outline" className="capitalize">{selectedBackupForDetails.status}</Badge>
                </div>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg space-y-2 border">
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Storage Backend:</span>
                  <span className="font-semibold text-sky-700 dark:text-sky-300">
                    {selectedBackupForDetails.storage_backend === "r2" ? "Cloudflare R2 (S3-Compatible)" : "Local Filesystem Only"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">R2 Object Key:</span>
                  <span className="font-mono text-[11px] truncate max-w-xs text-slate-600 dark:text-slate-300" title={selectedBackupForDetails.storage_key}>
                    {selectedBackupForDetails.storage_key || "None (Local only)"}
                  </span>
                </div>
                {selectedBackupForDetails.r2_etag && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500 font-medium">R2 ETag:</span>
                    <span className="font-mono text-[11px] text-slate-600 dark:text-slate-300">
                      {selectedBackupForDetails.r2_etag}
                    </span>
                  </div>
                )}
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Archive Size:</span>
                  <span className="font-mono font-semibold">
                    {formatBytes(selectedBackupForDetails.size_bytes)} ({selectedBackupForDetails.size_bytes.toLocaleString()} bytes)
                  </span>
                </div>
              </div>

              <div className="p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg space-y-2 border">
                <div>
                  <div className="text-slate-500 font-medium mb-1">SHA-256 Checksum:</div>
                  <div className="flex items-center gap-1 font-mono text-[11px] bg-white dark:bg-slate-900 p-2 rounded border break-all">
                    <span>{selectedBackupForDetails.checksum_sha256}</span>
                    <button
                      onClick={() => copyChecksum(selectedBackupForDetails.checksum_sha256)}
                      className="ml-auto p-1 hover:text-slate-900 text-slate-500 shrink-0"
                      title="Copy Checksum"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
                <div className="flex justify-between items-center pt-1">
                  <span className="text-slate-500 font-medium">Retention Policy:</span>
                  <span>
                    {selectedBackupForDetails.is_protected ? (
                      <Badge variant="outline" className="bg-purple-50 text-purple-700 border-purple-200">
                        Shielded (Exempt from pruning)
                      </Badge>
                    ) : selectedBackupForDetails.retention_until ? (
                      `Retain until ${new Date(selectedBackupForDetails.retention_until).toLocaleDateString()}`
                    ) : (
                      "Default 30 Days"
                    )}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Created:</span>
                  <span>{new Date(selectedBackupForDetails.created_at).toLocaleString()}</span>
                </div>
                {selectedBackupForDetails.completed_at && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500 font-medium">Completed:</span>
                    <span>{new Date(selectedBackupForDetails.completed_at).toLocaleString()}</span>
                  </div>
                )}
                {selectedBackupForDetails.verification_message && (
                  <div className="pt-1">
                    <span className="text-slate-500 font-medium">Verification Details:</span>
                    <p className="mt-0.5 text-slate-600 dark:text-slate-400 font-mono text-[11px]">
                      {selectedBackupForDetails.verification_message}
                    </p>
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-between items-center pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleToggleProtect(selectedBackupForDetails)}
                className="gap-1.5 text-xs text-purple-700 hover:bg-purple-50 border-purple-200"
              >
                <Shield className="h-3.5 w-3.5" />
                {selectedBackupForDetails.is_protected ? "Remove Shield" : "Protect Backup"}
              </Button>

              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleVerify(selectedBackupForDetails)}
                  className="text-xs"
                >
                  Verify Now
                </Button>
                <Button
                  size="sm"
                  variant="default"
                  onClick={() => setSelectedBackupForDetails(null)}
                  className="bg-slate-900 text-white text-xs"
                >
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal 3: Restore High Risk Modal */}
      {selectedBackupForRestore && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-amber-300 dark:border-amber-800 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-amber-600">
              <ShieldAlert className="h-6 w-6 shrink-0" />
              <div>
                <h3 className="font-bold text-base text-slate-900 dark:text-white">
                  FULL DATABASE RESTORE
                </h3>
                <p className="text-xs text-amber-700 font-semibold">
                  Critical Administrative Action — Replaces Live State
                </p>
              </div>
            </div>

            <div className="p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-xs text-amber-900 dark:text-amber-200 space-y-1.5">
              <div>
                Target Backup: <span className="font-bold">{selectedBackupForRestore.name}</span> (
                {formatBytes(selectedBackupForRestore.size_bytes)})
              </div>
              <div>
                Storage: <span className="font-medium">{selectedBackupForRestore.storage_backend === "r2" ? "Cloudflare R2 (Off-Site)" : "Local Filesystem"}</span>
              </div>
              <div>
                Created: {new Date(selectedBackupForRestore.created_at).toLocaleString()}
              </div>
              <div>
                SHA-256 Verified: <span className="font-semibold">{selectedBackupForRestore.status === "verified" ? "YES (Integrity Confirmed)" : "UNVERIFIED"}</span>
              </div>
              <div className="font-semibold text-amber-950 dark:text-amber-100 mt-2">
                Safety Guarantee: A pre-restore safety snapshot will automatically be generated and replicated to Cloudflare R2 before the restoration begins, ensuring no data created in the interim is permanently lost.
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                To confirm full restore, type <span className="font-mono text-amber-700 font-bold">RESTORE DATABASE</span> below:
              </label>
              <Input
                placeholder="RESTORE DATABASE"
                value={restoreConfirmText}
                onChange={(e) => setRestoreConfirmText(e.target.value)}
                className="font-mono text-sm border-amber-300 focus-visible:ring-amber-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={isRestoring}
                onClick={() => setSelectedBackupForRestore(null)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={restoreConfirmText !== "RESTORE DATABASE" || isRestoring}
                onClick={handleRestore}
                className="bg-amber-600 hover:bg-amber-700 text-white font-semibold"
              >
                {isRestoring ? "Restoring Database..." : "Restore Database"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
