"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  HardDrive,
  ArrowLeft,
  RotateCcw,
  CheckCircle2,
  ShieldAlert,
  RefreshCw,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import toast from "react-hot-toast";
import {
  adminDataSafetyApi,
  RecoveryStatus,
  DatabaseBackup,
} from "@/lib/api/admin-data-safety";

export default function AdminEmergencyRecoveryPage() {
  const [recovery, setRecovery] = useState<RecoveryStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore Modal State
  const [selectedBackupForRestore, setSelectedBackupForRestore] = useState<DatabaseBackup | null>(null);
  const [restoreConfirmText, setRestoreConfirmText] = useState("");
  const [isRestoring, setIsRestoring] = useState(false);

  const fetchRecovery = async () => {
    try {
      setIsLoading(true);
      const data = await adminDataSafetyApi.getRecoveryStatus();
      setRecovery(data);
    } catch (err: any) {
      console.error("Failed to load recovery status:", err);
      toast.error(err.message || "Failed to load recovery status.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRecovery();
  }, []);

  const handleRestore = async () => {
    if (!selectedBackupForRestore) return;

    if (restoreConfirmText !== "RESTORE DATABASE") {
      toast.error("Please type RESTORE DATABASE exactly to confirm.");
      return;
    }

    try {
      setIsRestoring(true);
      toast.loading("Restoring snapshot...", { id: "emergency-restore" });
      const res = await adminDataSafetyApi.restoreBackup(
        selectedBackupForRestore.id,
        restoreConfirmText
      );
      toast.success(res.message || "Recovery point restored successfully!", { id: "emergency-restore" });
      setSelectedBackupForRestore(null);
      setRestoreConfirmText("");
      fetchRecovery();
    } catch (err: any) {
      toast.error(err.message || "Emergency restoration failed.", { id: "emergency-restore" });
    } finally {
      setIsRestoring(false);
    }
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
              Emergency Disaster Recovery Center
            </h1>
            <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200">
              Disaster Preparedness
            </Badge>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Review pre-restore safety snapshots, verified recovery points, and emergency restoration procedures.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchRecovery}
            disabled={isLoading}
            className="gap-1.5"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Storage Information Banner */}
      <div className="bg-slate-50 dark:bg-slate-900 border rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div>
          <div className="text-slate-500 font-semibold mb-0.5">Physical Storage Directory</div>
          <div className="font-mono text-slate-800 dark:text-slate-200 truncate max-w-xl">
            {recovery?.storage_directory || "backups/database/"}
          </div>
        </div>
        <div className="flex items-center gap-4 text-slate-500">
          <div>
            Trash Recoverable:{" "}
            <span className="font-bold text-slate-900 dark:text-white">
              {recovery?.trash_recoverable_items ?? 0}
            </span>
          </div>
          <div>
            Safety Snapshots:{" "}
            <span className="font-bold text-slate-900 dark:text-white">
              {recovery?.pre_restore_snapshots?.length ?? 0}
            </span>
          </div>
        </div>
      </div>

      {/* Pre-Restore Safety Snapshots */}
      <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-600" />
              <CardTitle className="text-base font-semibold">Pre-Restore Safety Snapshots</CardTitle>
            </div>
            <Badge variant="secondary" className="text-xs">
              Automatic Protection
            </Badge>
          </div>
          <CardDescription>
            Created automatically before any full database restore operation to preserve interim records.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!recovery?.pre_restore_snapshots || recovery.pre_restore_snapshots.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">
              <CheckCircle2 className="h-6 w-6 text-slate-400 mx-auto mb-2 opacity-50" />
              No pre-restore safety snapshots exist yet. They are created automatically when a restore is initiated.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900 text-slate-500 text-xs uppercase border-b">
                  <tr>
                    <th className="p-3">Snapshot Name</th>
                    <th className="p-3">Created</th>
                    <th className="p-3">Size</th>
                    <th className="p-3">Checksum</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-xs">
                  {recovery.pre_restore_snapshots.map((s) => (
                    <tr key={s.id} className="hover:bg-slate-50/50">
                      <td className="p-3 font-medium text-slate-900 dark:text-white">
                        {s.name}
                      </td>
                      <td className="p-3 text-slate-500">
                        {new Date(s.created_at).toLocaleString()}
                      </td>
                      <td className="p-3 text-slate-600 dark:text-slate-300 font-mono">
                        {formatBytes(s.size_bytes)}
                      </td>
                      <td className="p-3 font-mono text-slate-400">
                        {s.checksum_sha256 ? `${s.checksum_sha256.substring(0, 10)}...` : "-"}
                      </td>
                      <td className="p-3 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setSelectedBackupForRestore(s);
                            setRestoreConfirmText("");
                          }}
                          className="h-7 text-xs border-amber-300 text-amber-800 hover:bg-amber-50"
                        >
                          <RotateCcw className="h-3 w-3 mr-1" />
                          Rollback Here
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Verified Recovery Points */}
      <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
        <CardHeader>
          <div className="flex items-center gap-2">
            <HardDrive className="h-5 w-5 text-blue-600" />
            <CardTitle className="text-base font-semibold">Verified Recovery Points</CardTitle>
          </div>
          <CardDescription>
            Recent verified backups that have passed SHA-256 cryptographic integrity verification.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!recovery?.recovery_points || recovery.recovery_points.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-sm">
              No verified recovery points available. Create a backup from the Backups page.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 dark:bg-slate-900 text-slate-500 text-xs uppercase border-b">
                  <tr>
                    <th className="p-3">Backup Label</th>
                    <th className="p-3">Type</th>
                    <th className="p-3">Created</th>
                    <th className="p-3">Size</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y text-xs">
                  {recovery.recovery_points.map((b) => (
                    <tr key={b.id} className="hover:bg-slate-50/50">
                      <td className="p-3 font-medium text-slate-900 dark:text-white">
                        {b.name}
                      </td>
                      <td className="p-3 capitalize">{b.backup_type.replace(/_/g, " ")}</td>
                      <td className="p-3 text-slate-500">
                        {new Date(b.created_at).toLocaleString()}
                      </td>
                      <td className="p-3 text-slate-600 dark:text-slate-300 font-mono">
                        {formatBytes(b.size_bytes)}
                      </td>
                      <td className="p-3 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setSelectedBackupForRestore(b);
                            setRestoreConfirmText("");
                          }}
                          className="h-7 text-xs border-amber-300 text-amber-800 hover:bg-amber-50"
                        >
                          <RotateCcw className="h-3 w-3 mr-1" />
                          Emergency Restore
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Emergency Restoration Modal */}
      {selectedBackupForRestore && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-amber-300 dark:border-amber-800 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-amber-600">
              <ShieldAlert className="h-6 w-6 shrink-0" />
              <div>
                <h3 className="font-bold text-base text-slate-900 dark:text-white">
                  EMERGENCY DATABASE RECOVERY
                </h3>
                <p className="text-xs text-amber-700 font-semibold">
                  Restores database state to target snapshot point
                </p>
              </div>
            </div>

            <div className="p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-xs text-amber-900 dark:text-amber-200 space-y-1.5">
              <div>
                Target: <span className="font-bold">{selectedBackupForRestore.name}</span>
              </div>
              <div>
                Snapshot Created: {new Date(selectedBackupForRestore.created_at).toLocaleString()}
              </div>
              <div className="font-semibold text-amber-950 dark:text-amber-100 mt-2">
                A pre-restore safety snapshot will automatically be created before restoration begins.
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                To confirm recovery, type <span className="font-mono text-amber-700 font-bold">RESTORE DATABASE</span>:
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
                {isRestoring ? "Restoring..." : "Restore Snapshot"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
