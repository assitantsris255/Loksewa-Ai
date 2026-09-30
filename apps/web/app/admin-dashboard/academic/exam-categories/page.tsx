"use client";
import React, { useState, useEffect, useCallback } from "react";
import { Bookmark, Search, Loader2, MoreVertical, Plus, Edit, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuTrigger, DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { adminSyllabusApi, AdminExamCategory } from "@/lib/api/admin-syllabus";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";

type ModalMode = "create" | "edit" | "delete" | null;

export default function ExamCategoriesPage() {
  const [categories, setCategories] = useState<AdminExamCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  // Single modal state — mode controls which dialog is open
  const [modalMode, setModalMode] = useState<ModalMode>(null);
  const [selectedCat, setSelectedCat] = useState<AdminExamCategory | null>(null);

  // Form fields
  const [fname, setFname] = useState("");
  const [fdesc, setFdesc] = useState("");
  const [forder, setForder] = useState(0);
  const [factive, setFactive] = useState(true);

  // ── Helpers ────────────────────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await adminSyllabusApi.getCategories();
      setCategories(data);
    } catch {
      toast.error("Failed to load categories");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const closeModal = () => { setModalMode(null); setSelectedCat(null); };

  const openCreate = () => {
    setFname(""); setFdesc(""); setForder(categories.length); setFactive(true);
    setSelectedCat(null);
    setModalMode("create");
  };

  const openEdit = (cat: AdminExamCategory) => {
    setFname(cat.name);
    setFdesc(cat.description || "");
    setForder(cat.order);
    setFactive(cat.is_active);
    setSelectedCat(cat);
    setModalMode("edit");
  };

  const openDelete = (cat: AdminExamCategory) => {
    setSelectedCat(cat);
    setModalMode("delete");
  };

  // ── CRUD ───────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!fname.trim()) { toast.error("Name is required"); return; }
    setIsSaving(true);
    try {
      if (modalMode === "create") {
        await adminSyllabusApi.createCategory({
          name: fname, description: fdesc, order: forder, is_active: factive,
        });
        toast.success("Category created!");
      } else if (modalMode === "edit" && selectedCat) {
        await adminSyllabusApi.updateCategory(selectedCat.id, {
          name: fname, description: fdesc, order: forder, is_active: factive,
        });
        toast.success("Category updated!");
      }
      closeModal();
      await loadData();
    } catch (err: any) {
      toast.error(err?.message || "Failed to save category");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedCat) return;
    setIsSaving(true);
    try {
      await adminSyllabusApi.deleteCategory(selectedCat.id, true);
      setCategories((prev) => prev.filter((c) => c.id !== selectedCat.id));
      toast.success(`"${selectedCat.name}" deleted`);
      closeModal();
      await loadData();
    } catch (err: any) {
      toast.error(err?.message || "Failed to delete category");
    } finally {
      setIsSaving(false);
    }
  };

  // ── Derived ────────────────────────────────────────────────────────────────
  const filtered = searchTerm
    ? categories.filter(c => c.name.toLowerCase().includes(searchTerm.toLowerCase()))
    : categories;

  const activeCount = categories.filter(c => c.is_active).length;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#0B2545] flex items-center gap-2">
            <Bookmark className="w-6 h-6 text-[#D4A72C]" />
            Exam Categories
          </h1>
          <p className="text-slate-500 text-sm mt-1">Manage examination categories.</p>
        </div>
        <Button onClick={openCreate} className="gap-2 bg-[#D4A72C] text-[#0B2545] hover:bg-[#C49B1F]">
          <Plus className="w-4 h-4" /> New Category
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-slate-600 text-sm font-medium mb-1">Total Categories</p>
          <div className="text-2xl font-bold text-[#0B2545]">
            {isLoading ? <Skeleton className="h-8 w-14 my-0.5" /> : categories.length}
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-emerald-500">
          <p className="text-slate-600 text-sm font-medium mb-1">Active</p>
          <div className="text-2xl font-bold text-emerald-600">
            {isLoading ? <Skeleton className="h-8 w-14 my-0.5" /> : activeCount}
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-blue-500">
          <p className="text-slate-600 text-sm font-medium mb-1">Inactive</p>
          <div className="text-2xl font-bold text-blue-600">
            {isLoading ? <Skeleton className="h-8 w-14 my-0.5" /> : categories.length - activeCount}
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
        <div className="relative w-full">
          <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <Input
            placeholder="Search categories..."
            className="pl-9 bg-slate-50 border border-slate-200 text-slate-900 placeholder:text-slate-600"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50 hover:bg-slate-50">
                <TableHead className="text-slate-700">Name</TableHead>
                <TableHead className="text-slate-700">Description</TableHead>
                <TableHead className="text-slate-700">Order</TableHead>
                <TableHead className="text-slate-700">Status</TableHead>
                <TableHead className="text-right text-slate-700">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i} className="border-b border-slate-200">
                    <TableCell><Skeleton className="h-4 w-32" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-8" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-16 rounded" /></TableCell>
                    <TableCell className="text-right"><Skeleton className="h-8 w-8 ml-auto rounded" /></TableCell>
                  </TableRow>
                ))
              ) : filtered.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-32 text-center text-slate-500 bg-white">
                    No categories found.
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map((cat) => (
                  <TableRow key={cat.id} className="hover:bg-slate-50/50 border-b border-slate-200 group">
                    <TableCell>
                      <p className="font-semibold text-[#0B2545]">{cat.name}</p>
                    </TableCell>
                    <TableCell>
                      <p className="text-sm text-slate-600 max-w-xs truncate">
                        {cat.description || "No description"}
                      </p>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-slate-600">#{cat.order}</span>
                    </TableCell>
                    <TableCell>
                      <span className={`text-xs font-semibold px-2 py-1 rounded ${
                        cat.is_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-700"
                      }`}>
                        {cat.is_active ? "Active" : "Inactive"}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-slate-100"
                          >
                            <span className="sr-only">Open menu</span>
                            <MoreVertical className="h-4 w-4 text-slate-500" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          <DropdownMenuLabel>Actions</DropdownMenuLabel>
                          <DropdownMenuItem
                            className="cursor-pointer"
                            onClick={() => openEdit(cat)}
                          >
                            <Edit className="w-4 h-4 mr-2" /> Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="cursor-pointer text-red-600 focus:text-red-600 focus:bg-red-50"
                            onClick={() => openDelete(cat)}
                          >
                            <Trash2 className="w-4 h-4 mr-2" /> Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* ── Create / Edit Dialog ───────────────────────────────────────────────── */}
      <Dialog
        open={modalMode === "create" || modalMode === "edit"}
        onOpenChange={(open) => { if (!open) closeModal(); }}
      >
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>
              {modalMode === "create" ? "Create New Category" : `Edit "${selectedCat?.name}"`}
            </DialogTitle>
            <DialogDescription>
              {modalMode === "create"
                ? "Add a new top-level exam category."
                : "Update the category details below."}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="cat_name">Name <span className="text-red-500">*</span></Label>
              <Input
                id="cat_name"
                placeholder="e.g. Loksewa, Banking, Security"
                value={fname}
                onChange={e => setFname(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSave()}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="cat_desc">Description</Label>
              <Textarea
                id="cat_desc"
                placeholder="Optional description"
                rows={3}
                value={fdesc}
                onChange={e => setFdesc(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="cat_order">Order</Label>
              <Input
                id="cat_order"
                type="number"
                value={forder}
                onChange={e => setForder(parseInt(e.target.value) || 0)}
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="cat_active"
                checked={factive}
                onChange={e => setFactive(e.target.checked)}
                className="w-4 h-4 accent-[#0B2545]"
              />
              <Label htmlFor="cat_active" className="cursor-pointer">
                Active (Visible to students)
              </Label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeModal} disabled={isSaving}>Cancel</Button>
            <Button
              className="bg-[#0B2545] hover:bg-[#0B2545]/90 text-white"
              onClick={handleSave}
              disabled={isSaving}
              aria-busy={isSaving}
            >
              {isSaving
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</>
                : modalMode === "create" ? "Create Category" : "Save Changes"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete Confirmation Dialog ─────────────────────────────────────────── */}
      <Dialog
        open={modalMode === "delete"}
        onOpenChange={(open) => { if (!open) closeModal(); }}
      >
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle className="text-red-600 flex items-center gap-2">
              <Trash2 className="w-5 h-5" /> Delete Category
            </DialogTitle>
            <DialogDescription asChild>
              <div className="pt-2 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                <p>
                  Are you sure you want to permanently delete{" "}
                  <strong className="text-[#0B2545] dark:text-white font-semibold">
                    {selectedCat ? `"${selectedCat.name}"` : "this category"}
                  </strong>?
                </p>
                <p className="text-amber-600 font-medium">
                  ⚠️ All positions, subjects, chapters and topics inside will also be deleted.
                </p>
                <p className="text-red-600 font-medium">This action cannot be undone.</p>
              </div>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={closeModal} disabled={isSaving}>Cancel</Button>
            <Button
              className="bg-red-600 hover:bg-red-700 text-white"
              onClick={handleDelete}
              disabled={isSaving}
              aria-busy={isSaving}
            >
              {isSaving
                ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Deleting...</>
                : "Yes, Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
