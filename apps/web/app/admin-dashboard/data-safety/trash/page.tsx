"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Trash2,
  ArchiveRestore,
  Search,
  AlertTriangle,
  Lock,
  CheckCircle2,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ShieldAlert,
  Info,
  X,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import toast from "react-hot-toast";
import {
  adminDataSafetyApi,
  TrashItem,
} from "@/lib/api/admin-data-safety";

export default function AdminTrashPage() {
  const [items, setItems] = useState<TrashItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [selectedModule, setSelectedModule] = useState("");
  const [protectedFilter, setProtectedFilter] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  // Modals & Actions
  const [selectedItemForDetails, setSelectedItemForDetails] = useState<TrashItem | null>(null);
  const [selectedItemForPermDelete, setSelectedItemForPermDelete] = useState<TrashItem | null>(null);
  const [permDeleteConfirmText, setPermDeleteConfirmText] = useState("");
  const [isDeletingPermanently, setIsDeletingPermanently] = useState(false);

  // Parent restore prompt state
  const [parentRestorePrompt, setParentRestorePrompt] = useState<{
    item: TrashItem;
    message: string;
  } | null>(null);

  const fetchTrashItems = async () => {
    try {
      setIsLoading(true);
      const params: any = { page };
      if (search) params.search = search;
      if (selectedModule) params.module = selectedModule;
      if (protectedFilter === "protected") params.is_protected = true;
      if (protectedFilter === "unprotected") params.is_protected = false;

      const res = await adminDataSafetyApi.getTrashItems(params);
      setItems(res.results || []);
      setTotalCount(res.count || 0);
    } catch (err: any) {
      console.error("Failed to fetch trash items:", err);
      toast.error(err.message || "Failed to load Recycle Bin items.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTrashItems();
  }, [page, selectedModule, protectedFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchTrashItems();
  };

  const handleRestore = async (item: TrashItem, restoreParents: boolean = false) => {
    try {
      toast.loading(`Restoring ${item.title}...`, { id: `restore-${item.id}` });
      const res = await adminDataSafetyApi.restoreTrashItem(item.id, restoreParents);

      if (res.needs_parent_restoration) {
        toast.dismiss(`restore-${item.id}`);
        setParentRestorePrompt({
          item,
          message: res.message || "Parent item is also in Trash. Restore parent as well?",
        });
        return;
      }

      toast.success(res.message || `${item.title} restored successfully!`, { id: `restore-${item.id}` });
      setParentRestorePrompt(null);
      fetchTrashItems();
    } catch (err: any) {
      if (err.data?.needs_parent_restoration) {
        toast.dismiss(`restore-${item.id}`);
        setParentRestorePrompt({
          item,
          message: err.data.message || "Parent item is in Trash. Restore parent as well?",
        });
        return;
      }
      toast.error(err.message || "Failed to restore record.", { id: `restore-${item.id}` });
    }
  };

  const handlePermanentDelete = async () => {
    if (!selectedItemForPermDelete) return;

    if (permDeleteConfirmText !== "DELETE PERMANENTLY") {
      toast.error("Please type DELETE PERMANENTLY exactly as shown to proceed.");
      return;
    }

    try {
      setIsDeletingPermanently(true);
      toast.loading("Permanently deleting record...", { id: "perm-del" });
      const res = await adminDataSafetyApi.permanentDeleteTrashItem(
        selectedItemForPermDelete.id,
        permDeleteConfirmText
      );
      toast.success(res.message || "Record permanently deleted.", { id: "perm-del" });
      setSelectedItemForPermDelete(null);
      setPermDeleteConfirmText("");
      fetchTrashItems();
    } catch (err: any) {
      toast.error(err.message || "Failed to permanently delete record.", { id: "perm-del" });
    } finally {
      setIsDeletingPermanently(false);
    }
  };

  const modules = ["Academic", "Exams", "Courses", "Notes", "Packages", "Marketplace"];

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
              Trash / Recycle Bin
            </h1>
            <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
              {totalCount} Items
            </Badge>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Safely soft-deleted business records. All data can be restored with its dependency tree intact.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => fetchTrashItems()}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col md:flex-row gap-3 items-center justify-between">
        <form onSubmit={handleSearchSubmit} className="flex gap-2 w-full md:w-96">
          <div className="relative w-full">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <Input
              placeholder="Search by title, type, reason..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 text-sm"
            />
          </div>
          <Button type="submit" variant="secondary" size="sm">
            Search
          </Button>
        </form>

        <div className="flex flex-wrap items-center gap-2 w-full md:w-auto">
          {/* Module Filter */}
          <select
            value={selectedModule}
            onChange={(e) => {
              setSelectedModule(e.target.value);
              setPage(1);
            }}
            className="h-9 px-3 rounded-md border text-xs bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200"
          >
            <option value="">All Modules</option>
            {modules.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>

          {/* Protection Filter */}
          <select
            value={protectedFilter}
            onChange={(e) => {
              setProtectedFilter(e.target.value);
              setPage(1);
            }}
            className="h-9 px-3 rounded-md border text-xs bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800 text-slate-700 dark:text-slate-200"
          >
            <option value="">All Statuses</option>
            <option value="protected">Shielded (Historical Data)</option>
            <option value="unprotected">Eligible for Permanent Deletion</option>
          </select>
        </div>
      </div>

      {/* Trash Table */}
      <Card className="border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-600 dark:text-slate-400 font-semibold border-b">
              <tr>
                <th className="p-3.5">Item & Type</th>
                <th className="p-3.5">Module</th>
                <th className="p-3.5">Deleted By</th>
                <th className="p-3.5">Deleted Date</th>
                <th className="p-3.5">Safety Status</th>
                <th className="p-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500">
                    Loading Recycle Bin contents...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-12 text-center text-slate-500">
                    <Trash2 className="h-8 w-8 mx-auto text-slate-400 mb-2 opacity-50" />
                    <p className="font-medium text-slate-700 dark:text-slate-300">Recycle Bin is empty</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Deleted academic and configuration records will appear here for safe recovery.
                    </p>
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr
                    key={item.id}
                    className="hover:bg-slate-50/70 dark:hover:bg-slate-900/40 transition-colors"
                  >
                    <td className="p-3.5">
                      <div className="font-medium text-slate-900 dark:text-white flex items-center gap-2">
                        {item.title}
                        {item.parent_info && (
                          <span className="text-xs text-slate-400 font-normal">
                            (under {item.parent_info.title})
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
                        <Badge variant="secondary" className="text-[10px] py-0 px-1.5">
                          {item.item_type}
                        </Badge>
                        {item.reason && <span className="italic">&ldquo;{item.reason}&rdquo;</span>}
                      </div>
                    </td>

                    <td className="p-3.5">
                      <Badge variant="outline" className="text-xs">
                        {item.module}
                      </Badge>
                    </td>

                    <td className="p-3.5 text-slate-600 dark:text-slate-300 text-xs">
                      {item.deleted_by_name || "Admin"}
                    </td>

                    <td className="p-3.5 text-slate-500 text-xs">
                      {new Date(item.deleted_at).toLocaleString([], {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </td>

                    <td className="p-3.5">
                      {item.is_protected ? (
                        <div className="flex items-center gap-1.5 text-purple-700 dark:text-purple-300 font-medium text-xs">
                          <Lock className="h-3.5 w-3.5 shrink-0" />
                          <span>Shielded</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-xs">
                          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                          <span>Recoverable</span>
                        </div>
                      )}
                    </td>

                    <td className="p-3.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleRestore(item)}
                          className="text-xs h-7 px-2.5 gap-1 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                        >
                          <ArchiveRestore className="h-3.5 w-3.5" />
                          Restore
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setSelectedItemForDetails(item)}
                          className="text-xs h-7 px-2 text-slate-500 hover:text-slate-800"
                        >
                          <Info className="h-3.5 w-3.5" />
                        </Button>

                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={item.is_protected}
                          onClick={() => {
                            setSelectedItemForPermDelete(item);
                            setPermDeleteConfirmText("");
                          }}
                          className={`text-xs h-7 px-2 ${
                            item.is_protected
                              ? "text-slate-300 cursor-not-allowed"
                              : "text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                          }`}
                          title={
                            item.is_protected
                              ? "Permanent deletion blocked: historical attempts depend on this record."
                              : "Permanent Delete (Super Admin only)"
                          }
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

      {/* Modal 1: Details & Dependency Breakdown */}
      {selectedItemForDetails && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border rounded-xl max-w-lg w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b pb-3">
              <div>
                <h3 className="font-semibold text-base text-slate-900 dark:text-white">
                  Record Metadata & Dependencies
                </h3>
                <p className="text-xs text-slate-500">Trash Reference #{selectedItemForDetails.id}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSelectedItemForDetails(null)}
                className="h-7 w-7 p-0"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-3 gap-2 py-1 border-b">
                <span className="text-slate-500 text-xs">Title:</span>
                <span className="col-span-2 font-medium text-slate-900 dark:text-white">
                  {selectedItemForDetails.title}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 py-1 border-b">
                <span className="text-slate-500 text-xs">Type & Model:</span>
                <span className="col-span-2 text-xs">
                  {selectedItemForDetails.item_type} ({selectedItemForDetails.model_name})
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 py-1 border-b">
                <span className="text-slate-500 text-xs">Module:</span>
                <span className="col-span-2 text-xs">{selectedItemForDetails.module}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 py-1 border-b">
                <span className="text-slate-500 text-xs">Deleted By:</span>
                <span className="col-span-2 text-xs">{selectedItemForDetails.deleted_by_name}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 py-1 border-b">
                <span className="text-slate-500 text-xs">Protection Status:</span>
                <div className="col-span-2">
                  {selectedItemForDetails.is_protected ? (
                    <div className="text-xs text-purple-600 dark:text-purple-400 font-medium">
                      Protected from permanent deletion
                    </div>
                  ) : (
                    <div className="text-xs text-emerald-600 font-medium">Eligible for permanent deletion</div>
                  )}
                  {selectedItemForDetails.protection_reason && (
                    <div className="text-xs text-slate-500 mt-0.5">
                      {selectedItemForDetails.protection_reason}
                    </div>
                  )}
                </div>
              </div>

              {/* Dependent counts */}
              {selectedItemForDetails.dependent_counts && (
                <div className="mt-3">
                  <div className="text-xs font-semibold text-slate-600 mb-1">Dependent Relationships:</div>
                  <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg text-xs space-y-1">
                    {Object.entries(selectedItemForDetails.dependent_counts).map(([key, val]) => (
                      <div key={key} className="flex justify-between">
                        <span className="capitalize">{key.replace(/_/g, " ")}:</span>
                        <span className="font-semibold">{String(val)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedItemForDetails(null)}
              >
                Close
              </Button>
              <Button
                size="sm"
                onClick={() => {
                  const it = selectedItemForDetails;
                  setSelectedItemForDetails(null);
                  handleRestore(it);
                }}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                Restore Now
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 2: Parent Restore Prompt */}
      {parentRestorePrompt && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border rounded-xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center gap-3 text-amber-600">
              <AlertTriangle className="h-6 w-6 shrink-0" />
              <h3 className="font-semibold text-base text-slate-900 dark:text-white">
                Parent Hierarchy in Trash
              </h3>
            </div>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {parentRestorePrompt.message}
            </p>
            <p className="text-xs text-slate-500">
              Restoring this item without its parent will leave it unattached. Would you like to restore both the parent and this item together?
            </p>

            <div className="flex justify-end gap-2 pt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setParentRestorePrompt(null)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={() => handleRestore(parentRestorePrompt.item, true)}
                className="bg-blue-600 hover:bg-blue-700 text-white"
              >
                Restore Parent & Item
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 3: Permanent Delete Protected Modal */}
      {selectedItemForPermDelete && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-rose-300 dark:border-rose-900 rounded-xl max-w-lg w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-rose-600">
              <ShieldAlert className="h-6 w-6 shrink-0" />
              <div>
                <h3 className="font-bold text-base text-slate-900 dark:text-white">
                  Permanent Delete Confirmation
                </h3>
                <p className="text-xs text-rose-600 font-semibold">
                  This action is irreversible and permanently erases data.
                </p>
              </div>
            </div>

            <div className="p-3 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 rounded-lg text-xs text-rose-900 dark:text-rose-200 space-y-1">
              <div>
                Target: <span className="font-bold">{selectedItemForPermDelete.title}</span> (
                {selectedItemForPermDelete.item_type})
              </div>
              <div>
                Only Super Administrators can execute permanent deletion. Once purged, recovery is only possible via a full database restore.
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                To confirm permanent deletion, type <span className="font-mono text-rose-600">DELETE PERMANENTLY</span> below:
              </label>
              <Input
                placeholder="DELETE PERMANENTLY"
                value={permDeleteConfirmText}
                onChange={(e) => setPermDeleteConfirmText(e.target.value)}
                className="font-mono text-sm border-rose-300 focus-visible:ring-rose-500"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={isDeletingPermanently}
                onClick={() => setSelectedItemForPermDelete(null)}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={
                  permDeleteConfirmText !== "DELETE PERMANENTLY" || isDeletingPermanently
                }
                onClick={handlePermanentDelete}
                className="bg-rose-600 hover:bg-rose-700 text-white font-semibold"
              >
                {isDeletingPermanently ? "Permanently Deleting..." : "Delete Permanently"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
