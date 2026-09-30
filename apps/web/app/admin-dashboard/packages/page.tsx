"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Plus,
  Pencil,
  Eye,
  EyeOff,
  Package as PackageIcon,
  Loader2,
  Check,
  X,
  Search,
  BookOpen,
  Layers,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import toast from "react-hot-toast";
import {
  subscriptionsApi,
  SubscriptionPlan,
  SubscriptionPlanInput,
} from "@/lib/api/subscriptions";
import { publicApi, PublicCourse } from "@/lib/api/public-api";
import { adminSyllabusApi, AdminExamCategory, AdminPosition } from "@/lib/api/admin-syllabus";

const EMPTY_FORM: SubscriptionPlanInput = {
  name: "",
  description: "",
  duration: 30,
  duration_unit: "DAYS",
  price: "0",
  original_price: null,
  discount: "0",
  badge: "NONE",
  features: [],
  course: null,
  package_type: "SINGLE",
  eligible_courses: [],
  status: "INACTIVE",
  display_order: 0,
  is_flexible: false,
  allowed_preparation_count: 1,
};

const FEATURE_OPTIONS = [
  { key: "*", label: "Full Platform Access (all features)" },
  { key: "ai_tutor", label: "AI Tutor" },
  { key: "premium_materials", label: "Premium Study Materials" },
  { key: "advanced_mock_exam", label: "Advanced Mock Exams" },
  { key: "analytics", label: "Advanced Analytics" },
];

function getCourseLevel(
  course: PublicCourse,
  academicExamById: Map<number, AdminPosition>
): AdminPosition | null {
  if (!course.exam || course.status !== "published") return null;
  let exam = academicExamById.get(course.exam.id);
  if (!exam) return null;

  const visited = new Set<number>();
  while (true) {
    if (exam.status !== "active" || !exam.is_active) return null;
    if (exam.parent === null) return exam;
    if (visited.has(exam.id)) return null;
    visited.add(exam.id);
    const parent = academicExamById.get(exam.parent);
    if (!parent) return null;
    exam = parent;
  }
}

function getCourseLevelName(
  course: PublicCourse,
  academicExamById: Map<number, AdminPosition>
): string | null {
  return getCourseLevel(course, academicExamById)?.name || null;
}

export default function AdminPackagesPage() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [courses, setCourses] = useState<PublicCourse[]>([]);
  const [academicExams, setAcademicExams] = useState<AdminPosition[]>([]);
  const [allCategories, setAllCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<SubscriptionPlanInput>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [togglingPlanId, setTogglingPlanId] = useState<number | null>(null);
  const [planPendingDelete, setPlanPendingDelete] = useState<SubscriptionPlan | null>(null);
  const [deletingPlanId, setDeletingPlanId] = useState<number | null>(null);

  // Hierarchy filter & search state inside the modal
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [selectedLevel, setSelectedLevel] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const load = () => {
    setLoading(true);
    Promise.all([
      subscriptionsApi.adminListPlans(),
      publicApi.getCourses(),
      adminSyllabusApi.getCategories().catch(() => [] as AdminExamCategory[]),
      adminSyllabusApi.getPositions().catch(() => [] as AdminPosition[]),
    ])
      .then(([planData, coursesData, categoriesData, examsData]) => {
        setPlans([...planData].sort((a, b) => a.display_order - b.display_order));
        if (coursesData) setCourses(coursesData);
        setAcademicExams(examsData);
        if (categoriesData && categoriesData.length > 0) {
          const names = categoriesData
            .filter((cat) => cat.is_active)
            .sort((a, b) => (a.order || 0) - (b.order || 0))
            .map((cat) => cat.name);
          setAllCategories(names);
        }
      })
      .catch(() => toast.error("Failed to load packages."))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const academicExamById = useMemo(
    () => new Map(academicExams.map((exam) => [exam.id, exam])),
    [academicExams]
  );

  // Extract unique categories from both syllabus categories and loaded courses
  const availableCategories = useMemo(() => {
    const set = new Set<string>();
    allCategories.forEach((cat) => set.add(cat));
    courses.forEach((c) => {
      if (getCourseLevel(c, academicExamById) && c.exam?.category_name) {
        set.add(c.exam.category_name);
      }
    });
    return Array.from(set).sort((a, b) => {
      const idxA = allCategories.indexOf(a);
      const idxB = allCategories.indexOf(b);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      return a.localeCompare(b);
    });
  }, [allCategories, academicExamById, courses]);

  // Extract unique levels for the selected category
  const availableLevels = useMemo(() => {
    return academicExams
      .filter((exam) => {
        const matchesCategory =
          selectedCategory === "ALL" || exam.category_name === selectedCategory;
        return exam.is_active && exam.parent === null && matchesCategory;
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [academicExams, selectedCategory]);

  // Filter courses based on Category, Level, and Search Query
  const filteredCourses = useMemo(() => {
    return courses.filter((c) => {
      const levelName = getCourseLevelName(c, academicExamById);
      if (!getCourseLevel(c, academicExamById)) return false;
      if (selectedCategory !== "ALL" && c.exam?.category_name !== selectedCategory) {
        return false;
      }
      if (selectedLevel !== "ALL" && String(getCourseLevel(c, academicExamById)?.id) !== selectedLevel) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchTitle = c.title.toLowerCase().includes(q);
        const matchExam = c.exam?.title?.toLowerCase().includes(q) ?? false;
        const matchLevel = levelName?.toLowerCase().includes(q) ?? false;
        const matchCategory = c.exam?.category_name?.toLowerCase().includes(q) ?? false;
        return matchTitle || matchExam || matchLevel || matchCategory;
      }
      return true;
    });
  }, [courses, academicExamById, selectedCategory, selectedLevel, searchQuery]);

  // Courses currently selected in the form
  const selectedCoursesList = useMemo(() => {
    if (form.package_type === "SINGLE") {
      return courses.filter((c) => c.id === form.course);
    }
    return courses.filter((c) => form.eligible_courses.includes(c.id));
  }, [courses, form.package_type, form.course, form.eligible_courses]);

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM, display_order: plans.length });
    setSelectedCategory("ALL");
    setSelectedLevel("ALL");
    setSearchQuery("");
    setDialogOpen(true);
  };

  const openEdit = (plan: SubscriptionPlan) => {
    setEditingId(plan.id);
    const initialEligible = plan.eligible_courses || [];
    const initialCourse = plan.course;

    setForm({
      name: plan.name,
      description: plan.description,
      duration: plan.duration,
      duration_unit: plan.duration_unit,
      price: plan.price,
      original_price: plan.original_price,
      discount: plan.discount,
      badge: plan.badge,
      features: plan.features,
      course: initialCourse,
      package_type: plan.package_type,
      eligible_courses:
        plan.package_type === "SINGLE" && initialCourse && initialEligible.length === 0
          ? [initialCourse]
          : initialEligible,
      status: plan.status,
      display_order: plan.display_order,
      is_flexible: plan.is_flexible,
      allowed_preparation_count: plan.allowed_preparation_count,
    });
    setSelectedCategory("ALL");
    setSelectedLevel("ALL");
    setSearchQuery("");
    setDialogOpen(true);
  };

  const toggleFeature = (key: string) => {
    setForm((f) => ({
      ...f,
      features: f.features.includes(key)
        ? f.features.filter((k) => k !== key)
        : [...f.features, key],
    }));
  };

  const handleToggleCourse = (courseId: number) => {
    if (form.package_type === "SINGLE") {
      // Toggle single selection
      const isSame = form.course === courseId;
      setForm({
        ...form,
        course: isSame ? null : courseId,
        eligible_courses: isSame ? [] : [courseId],
      });
    } else {
      // Multi or Bundle selection
      const isSelected = form.eligible_courses.includes(courseId);
      const next = isSelected
        ? form.eligible_courses.filter((id) => id !== courseId)
        : [...form.eligible_courses, courseId];

      setForm({
        ...form,
        course: null,
        eligible_courses: next,
      });
    }
  };

  const handleRemoveSelectedCourse = (courseId: number) => {
    if (form.package_type === "SINGLE") {
      setForm({ ...form, course: null, eligible_courses: [] });
    } else {
      setForm({
        ...form,
        eligible_courses: form.eligible_courses.filter((id) => id !== courseId),
      });
    }
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("Package name is required.");
      return;
    }

    if (form.package_type === "SINGLE") {
      const selectedId = form.course || (form.eligible_courses.length === 1 ? form.eligible_courses[0] : null);
      if (!selectedId) {
        toast.error("Please select a preparation for this Single Preparation package.");
        return;
      }
      form.course = selectedId;
      form.eligible_courses = [selectedId];
    } else if (form.package_type === "MULTI" || form.package_type === "BUNDLE") {
      if (form.eligible_courses.length === 0) {
        toast.error(`Please select at least one eligible preparation for ${form.package_type} packages.`);
        return;
      }
      if (form.package_type === "MULTI" && (form.allowed_preparation_count < 1 || isNaN(form.allowed_preparation_count))) {
        toast.error("Allowed preparation count must be at least 1.");
        return;
      }
    } else if (form.package_type === "ALL_ACCESS") {
      form.course = null;
      form.eligible_courses = [];
    }

    setSaving(true);
    try {
      if (editingId) {
        await subscriptionsApi.adminUpdatePlan(editingId, form);
        toast.success("Package updated successfully.");
      } else {
        await subscriptionsApi.adminCreatePlan(form);
        toast.success("Package created successfully.");
      }
      setDialogOpen(false);
      load();
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : typeof err === "object" && err !== null && "detail" in err
          ? String((err as { detail: unknown }).detail)
          : "Failed to save package.";
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const togglePublish = async (plan: SubscriptionPlan) => {
    const nextStatus = plan.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
    setTogglingPlanId(plan.id);
    try {
      await subscriptionsApi.adminUpdatePlan(plan.id, { status: nextStatus });
      toast.success(nextStatus === "ACTIVE" ? "Package published." : "Package unpublished.");
      load();
    } catch {
      toast.error("Failed to update package status.");
    } finally {
      setTogglingPlanId(null);
    }
  };

  const deletePlan = async () => {
    if (!planPendingDelete) return;
    setDeletingPlanId(planPendingDelete.id);
    try {
      const result = await subscriptionsApi.adminDeletePlan(planPendingDelete.id);
      toast.success(
        result.archived
          ? "Package archived; purchase history was preserved."
          : "Package deleted."
      );
      setPlanPendingDelete(null);
      load();
    } catch (error: unknown) {
      toast.error(error instanceof Error ? error.message : "Failed to delete package.");
    } finally {
      setDeletingPlanId(null);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Package Management
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage access bundles using existing Courses; packages do not own academic content.
          </p>
        </div>
        <Button
          onClick={openCreate}
          className="gap-2 bg-[#0B2545] hover:bg-[#0B2545]/90 shrink-0 shadow-sm"
        >
          <Plus className="w-4 h-4" /> Create Package
        </Button>
      </div>

      {/* Package List */}
      {loading ? (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200 text-left text-slate-600 font-semibold">
                  <th className="px-5 py-3.5">Package &amp; Preparation</th>
                  <th className="px-5 py-3.5">Price</th>
                  <th className="px-5 py-3.5">Duration &amp; Type</th>
                  <th className="px-5 py-3.5">Included Features</th>
                  <th className="px-5 py-3.5">Status</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="hover:bg-slate-50/60">
                    <td className="px-5 py-4 min-w-[240px]">
                      <Skeleton className="h-4 w-36 mb-2" />
                      <Skeleton className="h-3 w-52" />
                    </td>
                    <td className="px-5 py-4">
                      <Skeleton className="h-4 w-20" />
                    </td>
                    <td className="px-5 py-4">
                      <Skeleton className="h-4 w-24 mb-1" />
                      <Skeleton className="h-3 w-16" />
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex gap-1">
                        <Skeleton className="h-5 w-16 rounded" />
                        <Skeleton className="h-5 w-16 rounded" />
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <Skeleton className="h-5 w-16 rounded-full" />
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex justify-end gap-1.5">
                        <Skeleton className="h-8 w-24 rounded" />
                        <Skeleton className="h-8 w-16 rounded" />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : plans.length === 0 ? (
        <div className="text-center py-20 border border-dashed border-slate-200 rounded-xl bg-white">
          <PackageIcon className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="font-medium text-slate-800">No packages yet</h3>
          <p className="text-slate-500 text-sm mt-1">
            Create your first package to start selling preparation access.
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200 text-left text-slate-600 font-semibold">
                  <th className="px-5 py-3.5">Package & Preparation</th>
                  <th className="px-5 py-3.5">Price</th>
                  <th className="px-5 py-3.5">Duration & Type</th>
                  <th className="px-5 py-3.5">Included Features</th>
                  <th className="px-5 py-3.5">Status</th>
                  <th className="px-5 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {plans.map((plan) => {
                  const courseDetail = plan.course_details;
                  const eligibleDetails = plan.eligible_courses_details || [];

                  return (
                    <tr key={plan.id} className="hover:bg-slate-50/60 transition-colors">
                      <td className="px-5 py-4 min-w-[240px]">
                        <div className="font-semibold text-[#0B2545] text-base leading-snug">
                          {plan.name}
                        </div>
                        {plan.badge !== "NONE" && (
                          <Badge
                            variant="outline"
                            className="mt-1 text-[10px] uppercase font-bold tracking-wider bg-slate-50 border-slate-300"
                          >
                            {plan.badge.replace("_", " ")}
                          </Badge>
                        )}

                        {/* Preparation / Hierarchy Scope info */}
                        <div className="mt-2 text-xs text-slate-600 space-y-0.5">
                          {plan.package_type === "SINGLE" && (
                            courseDetail ? (
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-medium text-slate-800">
                                  {courseDetail.title}
                                </span>
                                {courseDetail.hierarchy_path && (
                                  <span className="text-[11px] text-slate-400">
                                    ({courseDetail.hierarchy_path})
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-slate-400 italic">No preparation assigned</span>
                            )
                          )}

                          {(plan.package_type === "MULTI" || plan.package_type === "BUNDLE") && (
                            <div className="space-y-1">
                              <span className="font-medium text-slate-700">
                                {eligibleDetails.length}{" "}
                                {eligibleDetails.length === 1 ? "preparation" : "preparations"}{" "}
                                {plan.package_type === "MULTI" ? "eligible" : "bundled"}:
                              </span>
                              <div className="flex flex-wrap gap-1 mt-0.5">
                                {eligibleDetails.slice(0, 3).map((item) => (
                                  <span
                                    key={item.id}
                                    className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] bg-slate-100 text-slate-700 border border-slate-200"
                                    title={item.hierarchy_path || item.title}
                                  >
                                    {item.title}
                                  </span>
                                ))}
                                {eligibleDetails.length > 3 && (
                                  <span className="text-[11px] text-slate-400 self-center">
                                    +{eligibleDetails.length - 3} more
                                  </span>
                                )}
                              </div>
                            </div>
                          )}

                          {plan.package_type === "ALL_ACCESS" && (
                            <span className="inline-flex items-center gap-1 font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 text-[11px]">
                              <Sparkles className="w-3 h-3 text-emerald-600" />
                              All Platform Preparations
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="px-5 py-4 font-medium text-[#0B2545] whitespace-nowrap">
                        <div className="text-base font-semibold">Rs. {plan.price}</div>
                        {plan.original_price && (
                          <div className="text-xs text-slate-400 line-through">
                            Rs. {plan.original_price}
                          </div>
                        )}
                      </td>

                      <td className="px-5 py-4 text-slate-600 whitespace-nowrap">
                        <div className="font-medium text-slate-800">
                          {plan.duration} {plan.duration_unit.toLowerCase()}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">
                          Type: <span className="font-semibold text-slate-700">{plan.package_type}</span>
                          {plan.package_type === "MULTI" && (
                            <span className="text-indigo-600 font-medium"> (Pick {plan.allowed_preparation_count})</span>
                          )}
                        </div>
                      </td>

                      <td className="px-5 py-4 text-slate-500 text-xs max-w-[200px]">
                        {plan.features.length ? (
                          <div className="flex flex-wrap gap-1">
                            {plan.features.map((feat) => (
                              <span
                                key={feat}
                                className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px]"
                              >
                                {feat === "*" ? "Full Access" : feat.replace("_", " ")}
                              </span>
                            ))}
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>

                      <td className="px-5 py-4 whitespace-nowrap">
                        <Badge
                          className={
                            plan.status === "ACTIVE"
                              ? "bg-emerald-100 text-emerald-800 border-none font-medium"
                              : "bg-slate-100 text-slate-500 border-none font-medium"
                          }
                        >
                          {plan.status === "ACTIVE"
                            ? "Published"
                            : plan.status === "ARCHIVED"
                            ? "Archived"
                            : "Draft"}
                        </Badge>
                      </td>

                      <td className="px-5 py-4 text-right space-x-1.5 whitespace-nowrap">
                        {plan.status !== "ARCHIVED" && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => togglePublish(plan)}
                            disabled={togglingPlanId === plan.id}
                            aria-busy={togglingPlanId === plan.id}
                            className="gap-1.5 text-xs h-8"
                          >
                            {togglingPlanId === plan.id ? (
                              <>
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                {plan.status === "ACTIVE" ? "Unpublishing..." : "Publishing..."}
                              </>
                            ) : plan.status === "ACTIVE" ? (
                              <>
                                <EyeOff className="w-3.5 h-3.5" /> Unpublish
                              </>
                            ) : (
                              <>
                                <Eye className="w-3.5 h-3.5" /> Publish
                              </>
                            )}
                          </Button>
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openEdit(plan)}
                          className="gap-1.5 text-xs h-8 border-slate-300 hover:border-slate-400"
                        >
                          <Pencil className="w-3.5 h-3.5" /> Edit
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setPlanPendingDelete(plan)}
                          disabled={deletingPlanId === plan.id}
                          aria-label={`Delete ${plan.name}`}
                          title="Delete package"
                          className="h-8 w-8 p-0 text-rose-700 hover:bg-rose-50 hover:border-rose-300"
                        >
                          {deletingPlanId === plan.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="w-3.5 h-3.5" />
                          )}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create / Edit Package Modal */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent
          className="admin-light-scope max-w-3xl w-full max-h-[92vh] flex flex-col p-0 overflow-hidden bg-white text-slate-900 shadow-2xl rounded-xl border border-slate-200"
        >
          {/* Header */}
          <DialogHeader className="px-6 py-4 border-b border-slate-200 bg-slate-50/70 shrink-0">
            <DialogTitle className="text-xl font-bold text-slate-900 flex items-center gap-2">
              <PackageIcon className="w-5 h-5 text-[#0B2545]" />
              {editingId ? "Edit Subscription Package" : "Create New Subscription Package"}
            </DialogTitle>
            <p className="text-xs text-slate-500 mt-0.5">
              Configure package pricing, duration, and academic preparation access scope.
            </p>
          </DialogHeader>

          {/* Modal Scrollable Body */}
          <div className="overflow-y-auto px-6 py-5 space-y-6 flex-1">
            {/* Section 1: Package Information */}
            <div className="space-y-4">
              <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
                <BookOpen className="w-4 h-4 text-[#0B2545]" />
                <h3 className="font-semibold text-sm text-slate-800">
                  Package Overview
                </h3>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-semibold text-slate-700">
                  Package Name <span className="text-rose-500">*</span>
                </Label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="e.g. PSC 5th Level Civil Engineering — 3 Months"
                  className="font-medium bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-semibold text-slate-700">
                  Description
                </Label>
                <Textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Comprehensive preparation package including all syllabus notes, practice sets, and mock exams."
                  rows={2}
                  className="bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-700">
                    Price (NPR) <span className="text-rose-500">*</span>
                  </Label>
                  <Input
                    type="number"
                    value={form.price}
                    onChange={(e) => setForm({ ...form, price: e.target.value })}
                    placeholder="e.g. 1999"
                    className="bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-700">
                    Original Price (NPR, optional)
                  </Label>
                  <Input
                    type="number"
                    value={form.original_price ?? ""}
                    onChange={(e) =>
                      setForm({ ...form, original_price: e.target.value || null })
                    }
                    placeholder="e.g. 2999"
                    className="bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-700">
                    Duration Value <span className="text-rose-500">*</span>
                  </Label>
                  <Input
                    type="number"
                    min={1}
                    value={form.duration}
                    onChange={(e) =>
                      setForm({ ...form, duration: parseInt(e.target.value) || 0 })
                    }
                    className="bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-700">
                    Duration Unit <span className="text-rose-500">*</span>
                  </Label>
                  <Select
                    value={form.duration_unit}
                    onValueChange={(v) =>
                      setForm({
                        ...form,
                        duration_unit: v as SubscriptionPlanInput["duration_unit"],
                      })
                    }
                  >
                    <SelectTrigger className="w-full bg-white text-slate-900 border-slate-300 focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]">
                      <SelectValue placeholder="Select duration unit" className="text-slate-900" />
                    </SelectTrigger>
                    <SelectContent className="bg-white text-slate-900 border-slate-200 shadow-xl">
                      <SelectItem value="DAYS" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Days</SelectItem>
                      <SelectItem value="WEEKS" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Weeks</SelectItem>
                      <SelectItem value="MONTHS" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Months</SelectItem>
                      <SelectItem value="YEAR" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Year</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-700">
                    Promotional Badge
                  </Label>
                  <Select
                    value={form.badge}
                    onValueChange={(v) =>
                      setForm({ ...form, badge: v as SubscriptionPlanInput["badge"] })
                    }
                  >
                    <SelectTrigger className="w-full bg-white text-slate-900 border-slate-300 focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]">
                      <SelectValue placeholder="Select badge" className="text-slate-900" />
                    </SelectTrigger>
                    <SelectContent className="bg-white text-slate-900 border-slate-200 shadow-xl">
                      <SelectItem value="NONE" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">None</SelectItem>
                      <SelectItem value="POPULAR" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Popular</SelectItem>
                      <SelectItem value="BEST_VALUE" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Best Value</SelectItem>
                      <SelectItem value="RECOMMENDED" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Recommended</SelectItem>
                      <SelectItem value="LIMITED_OFFER" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">Limited Offer</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-700">
                    Display Order
                  </Label>
                  <Input
                    type="number"
                    value={form.display_order}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        display_order: parseInt(e.target.value) || 0,
                      })
                    }
                    className="bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                  />
                </div>
              </div>
            </div>

            {/* Section 2: Package Type & Scope */}
            <div className="space-y-4 pt-2">
              <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
                <Layers className="w-4 h-4 text-[#0B2545]" />
                <h3 className="font-semibold text-sm text-slate-800">
                  Access Scope & Academic Structure
                </h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold text-slate-700">
                    Package Type <span className="text-rose-500">*</span>
                  </Label>
                  <Select
                    value={form.package_type}
                    onValueChange={(v) => {
                      const nextType = v as SubscriptionPlanInput["package_type"];
                      setForm({
                        ...form,
                        package_type: nextType,
                        course: null,
                        eligible_courses: [],
                      });
                    }}
                  >
                    <SelectTrigger className="w-full font-medium bg-white text-slate-900 border-slate-300 focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="bg-white text-slate-900 border-slate-200 shadow-xl">
                      <SelectItem value="SINGLE" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">
                        Single Preparation (Exact Match)
                      </SelectItem>
                      <SelectItem value="MULTI" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">
                        Multi Preparation (Student Selects N)
                      </SelectItem>
                      <SelectItem value="BUNDLE" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">
                        Bundle (All Selected Included)
                      </SelectItem>
                      <SelectItem value="ALL_ACCESS" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">
                        All Access (Full Platform)
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {form.package_type === "MULTI" && (
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-700">
                      Allowed Preparations to Choose <span className="text-rose-500">*</span>
                    </Label>
                    <Input
                      type="number"
                      min={1}
                      max={form.eligible_courses.length || 10}
                      value={form.allowed_preparation_count}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          allowed_preparation_count: parseInt(e.target.value) || 1,
                        })
                      }
                      className="font-medium bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                    />
                    <p className="text-[11px] text-slate-400">
                      Number of preparations the student can activate from the eligible pool.
                    </p>
                  </div>
                )}
              </div>

              {/* ALL_ACCESS Banner */}
              {form.package_type === "ALL_ACCESS" ? (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 text-emerald-900 flex items-start gap-3">
                  <Sparkles className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                  <div className="text-xs space-y-1">
                    <div className="font-semibold text-emerald-900 text-sm">
                      Full Academic All-Access Enabled
                    </div>
                    <p className="text-emerald-700 leading-relaxed">
                      Students who purchase or are assigned an All-Access package automatically receive unrestricted access to all current and future preparations, subjects, notes, and examinations across the entire LoksewaAI platform.
                    </p>
                  </div>
                </div>
              ) : (
                /* Preparation Selection Selector */
                <div className="space-y-3 bg-slate-50/70 p-4 rounded-xl border border-slate-200">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <Label className="text-xs font-bold text-slate-800 uppercase tracking-wide">
                        {form.package_type === "SINGLE"
                          ? "Select Target Preparation"
                          : form.package_type === "MULTI"
                          ? "Select Eligible Preparations Pool"
                          : "Select Preparations Included in Bundle"}
                      </Label>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {form.package_type === "SINGLE"
                          ? "Click a preparation to link this package directly to it."
                          : form.package_type === "MULTI"
                          ? `Select the candidate preparations students can choose from (Max ${form.allowed_preparation_count}).`
                          : "Select all preparations included in this bundle."}
                      </p>
                    </div>

                    {/* Selection Counter */}
                    <div className="shrink-0">
                      {form.package_type === "SINGLE" ? (
                        form.course ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                            <Check className="w-3.5 h-3.5" /> 1 Selected
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
                            None Selected
                          </span>
                        )
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800 border border-indigo-200">
                          {form.eligible_courses.length} Selected
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Filter & Search Bar */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
                    {/* Category Filter */}
                    <div>
                      <Select
                        value={selectedCategory}
                        onValueChange={(val) => {
                          setSelectedCategory(val);
                          setSelectedLevel("ALL");
                        }}
                      >
                        <SelectTrigger className="h-9 text-xs bg-white text-slate-900 border-slate-300 focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]">
                          <SelectValue placeholder="All Categories" className="text-slate-900" />
                        </SelectTrigger>
                        <SelectContent className="bg-white text-slate-900 border-slate-200 shadow-xl">
                          <SelectItem value="ALL" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">All Categories</SelectItem>
                          {availableCategories.map((cat) => (
                            <SelectItem key={cat} value={cat} className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">
                              {cat}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Level Filter */}
                    <div>
                      <Select
                        value={selectedLevel}
                        onValueChange={(val) => setSelectedLevel(val)}
                      >
                        <SelectTrigger className="h-9 text-xs bg-white text-slate-900 border-slate-300 focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]">
                          <SelectValue placeholder="All Levels" className="text-slate-900" />
                        </SelectTrigger>
                        <SelectContent className="bg-white text-slate-900 border-slate-200 shadow-xl">
                          <SelectItem value="ALL" className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">All Levels</SelectItem>
                          {availableLevels.map((lvl) => (
                            <SelectItem key={lvl.id} value={String(lvl.id)} className="text-slate-900 focus:bg-slate-100 focus:text-slate-900 cursor-pointer">
                              {lvl.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Search Input */}
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 absolute left-2.5 top-3 text-slate-400" />
                      <Input
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search preparation..."
                        className="h-9 pl-8 text-xs bg-white text-slate-900 border-slate-300 placeholder:text-slate-400 focus:bg-white focus:border-[#0B2545] focus:ring-1 focus:ring-[#0B2545]"
                      />
                      {searchQuery && (
                        <button
                          type="button"
                          onClick={() => setSearchQuery("")}
                          className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Selected Preparations Summary Chips */}
                  {selectedCoursesList.length > 0 && (
                    <div className="p-2.5 rounded-lg bg-white border border-slate-200 space-y-1.5 shadow-2xs">
                      <div className="text-[11px] font-semibold text-slate-600 flex items-center justify-between">
                        <span>Current Selection:</span>
                        <button
                          type="button"
                          onClick={() =>
                            setForm({ ...form, course: null, eligible_courses: [] })
                          }
                          className="text-[10px] text-rose-600 hover:underline"
                        >
                          Clear All
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedCoursesList.map((c) => (
                          <div
                            key={c.id}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs bg-[#0B2545]/5 text-[#0B2545] border border-[#0B2545]/20 font-medium"
                          >
                            <span>{c.title}</span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleRemoveSelectedCourse(c.id);
                              }}
                              className="text-slate-400 hover:text-rose-600"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Selectable Preparations Cards Container */}
                  {loading ? (
                    <div className="p-8 text-center text-xs text-slate-400">
                      Loading available preparations...
                    </div>
                  ) : courses.length === 0 ? (
                    <div className="p-8 text-center bg-white rounded-lg border border-dashed border-slate-200">
                      <p className="text-xs text-slate-500 font-medium">
                        No preparations available yet.
                      </p>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Publish a preparation in the syllabus before creating a package.
                      </p>
                    </div>
                  ) : filteredCourses.length === 0 ? (
                    <div className="p-8 text-center text-xs text-slate-400">
                      No preparations found matching the current filters.
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
                      {filteredCourses.map((c) => {
                        const isSelected =
                          form.package_type === "SINGLE"
                            ? form.course === c.id
                            : form.eligible_courses.includes(c.id);
                        const isCS = c.is_coming_soon;
                        const courseLevel = getCourseLevel(c, academicExamById);

                        return (
                          <div
                            key={c.id}
                            onClick={() => handleToggleCourse(c.id)}
                            className={`group relative rounded-xl p-3 transition-all cursor-pointer border flex items-start gap-3 text-left ${
                              isSelected
                                ? "border-[#0B2545] bg-[#0B2545]/5 shadow-xs ring-1 ring-[#0B2545]/30"
                                : isCS
                                ? "border-amber-200/80 bg-amber-50/40 hover:border-amber-300 hover:bg-amber-50/70"
                                : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80"
                            }`}
                          >
                            {/* Radio / Checkbox Indicator */}
                            <div className="pt-0.5 shrink-0">
                              <div
                                className={`w-4 h-4 rounded-${
                                  form.package_type === "SINGLE" ? "full" : "md"
                                } border flex items-center justify-center transition-colors ${
                                  isSelected
                                    ? "bg-[#0B2545] border-[#0B2545] text-white"
                                    : "border-slate-300 bg-white group-hover:border-slate-400"
                                }`}
                              >
                                {isSelected && (
                                  form.package_type === "SINGLE" ? (
                                    <div className="w-1.5 h-1.5 rounded-full bg-white" />
                                  ) : (
                                    <Check className="w-3 h-3 stroke-[3]" />
                                  )
                                )}
                              </div>
                            </div>

                            {/* Content */}
                            <div className="flex-1 min-w-0 space-y-1">
                              <div className="flex items-center justify-between gap-2 flex-wrap">
                                <span className="font-semibold text-slate-900 text-sm break-words leading-tight">
                                  {c.title}
                                </span>
                                {isCS ? (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 uppercase tracking-wider shrink-0">
                                    Coming Soon
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-800 border border-emerald-200 shrink-0">
                                    Published
                                  </span>
                                )}
                              </div>

                              {/* Hierarchy Breadcrumb: Category > Level > Preparation */}
                              <div className="text-xs text-slate-500 flex items-center gap-1.5 flex-wrap">
                                {c.exam?.category_name && (
                                  <span>{c.exam.category_name}</span>
                                )}
                                {courseLevel && courseLevel.id !== c.exam?.id && (
                                  <>
                                    <span className="text-slate-300">›</span>
                                    <span>{courseLevel.name}</span>
                                  </>
                                )}
                                {c.exam?.title && (
                                  <>
                                    <span className="text-slate-300">›</span>
                                    <span className="text-slate-700 font-medium">
                                      {c.exam.title}
                                    </span>
                                  </>
                                )}
                              </div>

                              {isCS && (
                                <p className="text-[11px] text-amber-700 font-normal">
                                  Preparation is in development. Students cannot purchase yet, but you can pre-configure packages.
                                </p>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Section 3: Included Platform Features */}
            <div className="space-y-3 pt-2">
              <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
                <Sparkles className="w-4 h-4 text-[#0B2545]" />
                <h3 className="font-semibold text-sm text-slate-800">
                  Included Features
                </h3>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 border border-slate-200 rounded-xl p-3.5 bg-slate-50/50">
                {FEATURE_OPTIONS.map((f) => {
                  const isChecked = form.features.includes(f.key);
                  return (
                    <label
                      key={f.key}
                      className={`flex items-center gap-2.5 p-2 rounded-lg text-xs font-medium cursor-pointer border transition-colors ${
                        isChecked
                          ? "bg-white border-[#0B2545]/30 text-[#0B2545] shadow-2xs"
                          : "bg-transparent border-transparent text-slate-600 hover:bg-white/60"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleFeature(f.key)}
                        className="rounded border-slate-300 text-[#0B2545] focus:ring-[#0B2545]"
                      />
                      <span>{f.label}</span>
                    </label>
                  );
                })}
              </div>
              <p className="text-[11px] text-slate-400">
                Selected features unlock platform capabilities (Notes, Exams, AI Tutor, Analytics) once package enforcement is enabled.
              </p>
            </div>
          </div>

          {/* Sticky Modal Footer */}
          <DialogFooter className="px-6 py-4 border-t border-slate-200 bg-slate-50 shrink-0 flex flex-row items-center justify-between sm:justify-between">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDialogOpen(false)}
              className="text-xs bg-white text-slate-700 border border-slate-300 hover:bg-slate-100 hover:text-slate-900 font-medium"
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="bg-[#0B2545] hover:bg-[#163E6C] text-white text-xs px-5 shadow-sm font-semibold"
            >
              {saving ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                  Saving...
                </>
              ) : editingId ? (
                "Save Package Changes"
              ) : (
                "Create Package"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(planPendingDelete)}
        onOpenChange={(open) => {
          if (!open && deletingPlanId === null) setPlanPendingDelete(null);
        }}
      >
        <DialogContent className="max-w-md bg-white text-slate-900">
          <DialogHeader>
            <DialogTitle>Delete Package?</DialogTitle>
            <DialogDescription>
              This removes the package from active listings. If subscriptions, payments, enrollments,
              course selections, or audit history depend on it, it will be archived instead so
              historical records remain intact.
            </DialogDescription>
          </DialogHeader>
          {planPendingDelete && (
            <p className="text-sm font-semibold text-slate-800">{planPendingDelete.name}</p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setPlanPendingDelete(null)}
              disabled={deletingPlanId !== null}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={deletePlan}
              disabled={deletingPlanId !== null}
              className="bg-rose-700 text-white hover:bg-rose-800"
            >
              {deletingPlanId !== null ? "Deleting..." : "Delete Package"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
