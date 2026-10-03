"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ShieldCheck,
  Trash2,
  HardDrive,
  ArchiveRestore,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Lock,
  ArrowRight,
  Clock,
  AlertOctagon,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import toast from "react-hot-toast";
import { adminDataSafetyApi, DataSafetyOverview } from "@/lib/api/admin-data-safety";

export default function DataSafetyOverviewPage() {
  const [overview, setOverview] = useState<DataSafetyOverview | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreatingBackup, setIsCreatingBackup] = useState(false);

  const fetchOverview = async () => {
    try {
      setIsLoading(true);
      const data = await adminDataSafetyApi.getOverview();
      setOverview(data);
    } catch (err: unknown) {
      console.error("Failed to load data safety overview:", err);
      const msg = err instanceof Error ? err.message : "Failed to load Data Safety status.";
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, []);

  const handleInstantBackup = async () => {
    try {
      setIsCreatingBackup(true);
      toast.loading("Generating full database snapshot...", { id: "backup-create" });
      const backup = await adminDataSafetyApi.createBackup({
        name: `Manual Admin Snapshot - ${new Date().toLocaleDateString()}`,
        backup_type: "manual",
      });
      toast.success(`Backup "${backup.name}" created and verified successfully!`, { id: "backup-create" });
      fetchOverview();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create database backup.";
      toast.error(msg, { id: "backup-create" });
    } finally {
      setIsCreatingBackup(false);
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
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Data Safety & Disaster Recovery
            </h1>
            <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200">
              Active Protection
            </Badge>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Centralized safe-delete trash architecture, relational cascade shields, and verified database recovery.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchOverview}
            disabled={isLoading}
            className="gap-2"
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>

          <Button
            size="sm"
            onClick={handleInstantBackup}
            disabled={isCreatingBackup}
            className="gap-2 bg-slate-900 hover:bg-slate-800 text-white"
          >
            <HardDrive className="h-4 w-4" />
            {isCreatingBackup ? "Creating..." : "Instant Backup"}
          </Button>
        </div>
      </div>

      {/* Warnings Banner if any */}
      {overview?.safety_warnings && overview.safety_warnings.length > 0 && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 text-sm text-amber-900 dark:text-amber-200">
            <div className="font-semibold mb-1">Attention Required: Data Safety Advisory</div>
            <ul className="list-disc list-inside space-y-1">
              {overview.safety_warnings.map((warn, i) => (
                <li key={i}>{warn}</li>
              ))}
            </ul>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleInstantBackup}
            className="border-amber-300 hover:bg-amber-100 text-amber-900 text-xs shrink-0"
          >
            Run Backup Now
          </Button>
        </div>
      )}

      {/* Real Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Backup Status */}
        <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Backup Health</CardTitle>
            {overview?.backup_status === "healthy" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            ) : overview?.backup_status === "warning" ? (
              <AlertTriangle className="h-4 w-4 text-amber-500" />
            ) : (
              <AlertOctagon className="h-4 w-4 text-rose-500" />
            )}
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize text-slate-900 dark:text-white">
              {overview?.backup_status || "Checking..."}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {overview?.last_backup ? (
                <>
                  Latest: {new Date(overview.last_backup.created_at).toLocaleDateString()} (
                  {formatBytes(overview.last_backup.size_bytes)})
                </>
              ) : (
                "No verified backups recorded"
              )}
            </p>
          </CardContent>
        </Card>

        {/* Cloudflare R2 Off-site Storage */}
        <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Cloudflare R2 Off-Site</CardTitle>
            <HardDrive className={`h-4 w-4 ${overview?.r2_configured ? "text-sky-500" : "text-slate-400"}`} />
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold text-slate-900 dark:text-white">
                {overview?.r2_configured ? "Active" : "Not Configured"}
              </span>
              <Badge
                variant="outline"
                className={`text-[10px] ${
                  overview?.r2_configured
                    ? "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300"
                    : "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400"
                }`}
              >
                {overview?.r2_configured ? "S3-Compatible" : "Local Staging"}
              </Badge>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {overview?.r2_configured
                ? `${overview.r2_verified_count ?? 0} off-site verified snapshots`
                : "Backups reside on local application server"}
            </p>
          </CardContent>
        </Card>

        {/* Retention & Shielded Records */}
        <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Retention & Shields</CardTitle>
            <Lock className="h-4 w-4 text-purple-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-slate-900 dark:text-white">
              {overview?.retention_days ?? 30} Days
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {overview?.protected_backups_count ?? 0} protected backups &bull; {overview?.protected_records_count ?? 0} trash shields
            </p>
          </CardContent>
        </Card>

        {/* Trash / Recycle Bin */}
        <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-slate-500">Trash / Recycle Bin</CardTitle>
            <Trash2 className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-slate-900 dark:text-white">
              {overview?.trash_items_count ?? 0}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {overview?.recently_restored_count ?? 0} restored in past 7 days
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Navigation Modules */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Module 1: Trash / Recycle Bin */}
        <Card className="border border-slate-200 dark:border-slate-800 hover:border-blue-400 transition-all shadow-sm">
          <CardHeader>
            <div className="h-10 w-10 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center text-blue-600 mb-2">
              <Trash2 className="h-5 w-5" />
            </div>
            <CardTitle className="text-lg">Trash / Recycle Bin</CardTitle>
            <CardDescription>
              Review soft-deleted academic categories, exams, questions, notes, and study packages.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="text-xs text-slate-500 space-y-1.5 list-disc list-inside">
              <li>1-click reversible restoration</li>
              <li>Hierarchical parent dependency warnings</li>
              <li>Super Admin typed confirmation for permanent delete</li>
            </ul>
            <Link href="/admin-dashboard/data-safety/trash">
              <Button variant="outline" className="w-full justify-between mt-2">
                Open Recycle Bin
                <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardContent>
        </Card>

        {/* Module 2: Database Backups */}
        <Card className="border border-slate-200 dark:border-slate-800 hover:border-emerald-400 transition-all shadow-sm">
          <CardHeader>
            <div className="h-10 w-10 rounded-lg bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center text-emerald-600 mb-2">
              <HardDrive className="h-5 w-5" />
            </div>
            <CardTitle className="text-lg">Database Backups</CardTitle>
            <CardDescription>
              Real gzip-compressed database snapshots with streaming SHA-256 cryptographic verification.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="text-xs text-slate-500 space-y-1.5 list-disc list-inside">
              <li>Verified archive integrity and sizes</li>
              <li>Automatic pre-restore safety snapshots</li>
              <li>Protected downloads for Super Admins</li>
            </ul>
            <Link href="/admin-dashboard/data-safety/backups">
              <Button variant="outline" className="w-full justify-between mt-2">
                Manage Backups
                <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardContent>
        </Card>

        {/* Module 3: Emergency Recovery */}
        <Card className="border border-slate-200 dark:border-slate-800 hover:border-amber-400 transition-all shadow-sm">
          <CardHeader>
            <div className="h-10 w-10 rounded-lg bg-amber-50 dark:bg-amber-900/30 flex items-center justify-center text-amber-600 mb-2">
              <ArchiveRestore className="h-5 w-5" />
            </div>
            <CardTitle className="text-lg">Emergency Recovery</CardTitle>
            <CardDescription>
              Incident recovery center, safety snapshot catalog, and disaster recovery audit trails.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ul className="text-xs text-slate-500 space-y-1.5 list-disc list-inside">
              <li>Pre-restore snapshot points</li>
              <li>Recovery health indicators</li>
              <li>Destructive action audit history</li>
            </ul>
            <Link href="/admin-dashboard/data-safety/recovery">
              <Button variant="outline" className="w-full justify-between mt-2">
                View Recovery Center
                <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* Safety Architecture & Last Permanent Delete Audit */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Architecture Flow */}
        <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-600" />
              Data Safety Guarantees
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
            <div className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border flex items-start gap-3">
              <div className="font-semibold text-slate-900 dark:text-white shrink-0">1. Safe Deletion:</div>
              <div>Admin deletes move records to Trash rather than running hard database CASCADE.</div>
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border flex items-start gap-3">
              <div className="font-semibold text-slate-900 dark:text-white shrink-0">2. History Shield:</div>
              <div>Any exam, question, or course with student attempts or answers is locked from permanent deletion.</div>
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-900 rounded-lg border flex items-start gap-3">
              <div className="font-semibold text-slate-900 dark:text-white shrink-0">3. Safe Restore:</div>
              <div>Before any database restore occurs, the system automatically writes a safety snapshot.</div>
            </div>
          </CardContent>
        </Card>

        {/* Last Permanent Deletion Audit */}
        <Card className="border border-slate-200 dark:border-slate-800 shadow-sm">
          <CardHeader>
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Clock className="h-5 w-5 text-slate-500" />
              Permanent Deletion Audit Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            {overview?.last_permanent_delete ? (
              <div className="space-y-2 p-4 bg-slate-50 dark:bg-slate-900 rounded-lg border text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-slate-500">Record:</span>
                  <span className="font-semibold text-slate-900 dark:text-white">
                    {overview.last_permanent_delete.title}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500">Type:</span>
                  <Badge variant="outline">{overview.last_permanent_delete.item_type}</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500">Authorized By:</span>
                  <span>{overview.last_permanent_delete.deleted_by}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500">Date:</span>
                  <span>{new Date(overview.last_permanent_delete.timestamp).toLocaleString()}</span>
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-slate-500 text-sm">
                No permanent deletion events have been recorded in the platform audit logs.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
