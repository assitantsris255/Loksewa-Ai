"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { BookMarked, Search, Plus, MoreVertical, Edit, Trash2, Eye, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { apiClient } from "@/lib/api/client";
import { ButtonSpinner } from "@/components/ui/loading-states";
import { Skeleton } from "@/components/ui/skeleton";

export default function AcademicTopicsPage() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createFormData, setCreateFormData] = useState({ title: "", description: "", order: 0 });
  const [topics, setTopics] = useState<any[]>([]);
  const [chapters, setChapters] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null);
  const [totalTopics, setTotalTopics] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const data = await apiClient<any>("/admin/syllabus/chapters/?page_size=100");
        const chaps = Array.isArray(data) ? data : (data.results || []);
        setChapters(chaps);
        if (chaps.length > 0) {
          setSelectedChapter(chaps[0].id);
        }
      } catch (error) {
        console.error("Failed to fetch chapters", error);
      }
    })();
  }, []);

  useEffect(() => {
    if (selectedChapter) {
      setCurrentPage(1);
      (async () => {
        try {
          const data = await apiClient<any>("/admin/syllabus/topics/?chapter=" + selectedChapter);
          const topicsList = Array.isArray(data) ? data : (data.results || []);
          setTopics(topicsList);
          setTotalTopics(data.count || topicsList.length || 0);
        } catch (error) {
          console.error("Failed to fetch topics", error);
        } finally {
          setIsLoading(false);
        }
      })();
    }
  }, [selectedChapter]);

  const activeTopics = topics.filter(t => t.is_active).length;
  const filteredTopics = searchTerm ? topics.filter(t => t.title.toLowerCase().includes(searchTerm.toLowerCase())) : topics;

  const handleCreateTopic = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedChapter) {
      alert("Please select a chapter first");
      return;
    }
    setIsSubmitting(true);
    try {
      await apiClient("/admin/syllabus/topics/", {
        method: "POST",
        body: JSON.stringify({
          chapter: selectedChapter,
          name: createFormData.title,
          description: createFormData.description,
          order: createFormData.order,
          is_active: true,
        }),
      });
      setShowCreateModal(false);
      setCreateFormData({ title: "", description: "", order: 0 });
      // Refresh topics
      if (selectedChapter) {
        const data = await apiClient<any>("/admin/syllabus/topics/?chapter=" + selectedChapter);
        const topicsList = Array.isArray(data) ? data : (data.results || []);
        setTopics(topicsList);
      }
    } catch (error) {
      console.error("Failed to create topic", error);
      alert("Failed to create topic");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#0B2545] flex items-center gap-2">
            <BookMarked className="w-6 h-6 text-[#D4A72C]" />
            Topics
          </h1>
          <p className="text-slate-500 text-sm mt-1">Manage topics within chapters.</p>
        </div>
        <Button
          onClick={() => setShowCreateModal(true)}
          disabled={!selectedChapter}
          className="gap-2 bg-[#D4A72C] text-[#0B2545] hover:bg-[#C49B1F]"
        >
          <Plus className="w-4 h-4" />
          New Topic
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <p className="text-slate-600 text-sm font-medium mb-1">Total Topics</p>
          <div className="text-2xl font-bold text-[#0B2545]">
            {isLoading ? <Skeleton className="h-8 w-14 my-0.5" /> : totalTopics}
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-emerald-500">
          <p className="text-slate-600 text-sm font-medium mb-1">Active</p>
          <div className="text-2xl font-bold text-emerald-600">
            {isLoading ? <Skeleton className="h-8 w-14 my-0.5" /> : activeTopics}
          </div>
        </div>
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm border-l-4 border-l-slate-400">
          <p className="text-slate-600 text-sm font-medium mb-1">Selected Chapter</p>
          <p className="text-lg font-bold text-slate-700">
            {chapters.find(c => c.id === selectedChapter)?.title || 'Select a chapter'}
          </p>
        </div>
      </div>

      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">Select Chapter</label>
          <select
            value={selectedChapter || ''}
            onChange={(e) => setSelectedChapter(e.target.value ? Number(e.target.value) : null)}
            className="w-full px-4 py-2 bg-white border border-slate-200 text-slate-900 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4A72C]"
          >
            <option value="">-- Choose a chapter --</option>
            {chapters.map(chapter => (
              <option key={chapter.id} value={chapter.id}>
                {chapter.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-slate-50 hover:bg-slate-50">
                <TableHead className="text-slate-700">Title</TableHead>
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
                    <TableCell><Skeleton className="h-4 w-36" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                    <TableCell><Skeleton className="h-4 w-8" /></TableCell>
                    <TableCell><Skeleton className="h-5 w-16 rounded" /></TableCell>
                    <TableCell className="text-right"><Skeleton className="h-8 w-8 ml-auto rounded" /></TableCell>
                  </TableRow>
                ))
              ) : !selectedChapter ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-32 text-center text-slate-500 bg-white">
                    Please select a chapter to view topics.
                  </TableCell>
                </TableRow>
              ) : filteredTopics.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-32 text-center text-slate-500 bg-white">
                    No topics found.
                  </TableCell>
                </TableRow>
              ) : (
                filteredTopics.map((topic) => (
                  <TableRow key={topic.id} className="hover:bg-slate-50/50 border-b border-slate-200">
                    <TableCell>
                      <p className="font-semibold text-[#0B2545]">{topic.title}</p>
                    </TableCell>
                    <TableCell>
                      <p className="text-sm text-slate-600 max-w-xs truncate">
                        {topic.description || 'No description'}
                      </p>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-slate-600">#{topic.order}</span>
                    </TableCell>
                    <TableCell>
                      <span className={topic.is_active ? 'bg-emerald-100 text-emerald-700 text-xs font-semibold px-2 py-1 rounded' : 'bg-slate-100 text-slate-700 text-xs font-semibold px-2 py-1 rounded'}>
                        {topic.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 hover:bg-slate-100">
                            <MoreVertical className="h-4 w-4 text-slate-500" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>Actions</DropdownMenuLabel>
                          <DropdownMenuItem className="cursor-pointer">
                            <Eye className="w-4 h-4 mr-2" /> View
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

      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-lg max-w-md w-full mx-4 p-6">
            <h2 className="text-xl font-bold text-[#0B2545] mb-4">Create New Topic</h2>
            <form onSubmit={handleCreateTopic} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Topic Title *</label>
                <Input
                  type="text"
                  placeholder="Enter topic title"
                  value={createFormData.title}
                  onChange={(e) => setCreateFormData({ ...createFormData, title: e.target.value })}
                  required
                  className="bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Description</label>
                <textarea
                  placeholder="Enter topic description (optional)"
                  value={createFormData.description}
                  onChange={(e) => setCreateFormData({ ...createFormData, description: e.target.value })}
                  rows={3}
                  className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#D4A72C] bg-slate-50 text-slate-900 placeholder:text-slate-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Order</label>
                <Input
                  type="number"
                  placeholder="0"
                  value={createFormData.order}
                  onChange={(e) => setCreateFormData({ ...createFormData, order: parseInt(e.target.value) })}
                  className="bg-slate-50 border-slate-200 text-slate-900"
                />
              </div>
              <div className="flex gap-3 pt-4">
                <Button
                  type="submit"
                  disabled={isSubmitting || !createFormData.title.trim()}
                  aria-busy={isSubmitting}
                  className="flex-1 bg-[#D4A72C] text-[#0B2545] hover:bg-[#C49B1F]"
                >
                  {isSubmitting ? <ButtonSpinner text="Creating..." /> : "Create Topic"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowCreateModal(false)}
                  disabled={isSubmitting}
                  className="flex-1"
                >
                  Cancel
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
