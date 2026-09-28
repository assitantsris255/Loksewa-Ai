"use client";

import { useState, useEffect } from "react";
import { CheckCircle2, XCircle, Clock, Eye, Gift, ImageIcon, X, ZoomIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient } from "@/lib/api/client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL?.replace("/api", "") || "http://127.0.0.1:8000";

interface Payment {
  id: number;
  student_name: string;
  plan_details: {
    name: string;
    duration: number;
    duration_unit: string;
  };
  payment_method_details: {
    display_name: string;
  };
  amount: string;
  transaction_id: string;
  screenshot: string | null;
  note: string;
  status: string;
  submitted_at: string;
  selected_courses?: { id: number; title: string }[];
}

interface CourseApplication {
  id: number;
  student: { id: number; name: string; username: string; email: string };
  course: { id: number; title: string };
  application_status: "pending" | "approved" | "rejected" | "cancelled";
  applied_at: string;
  payment: { id: number; status: string; amount: string; plan_name: string } | null;
}

type Row =
  | { kind: "payment"; id: number; data: Payment }
  | { kind: "free_application"; id: number; data: CourseApplication };

// ── Lightbox ─────────────────────────────────────────────────────────────────
function ScreenshotLightbox({ src, onClose }: { src: string; onClose: () => void }) {
  const fullUrl = src.startsWith("http") ? src : `${API_BASE}${src}`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-3xl w-full bg-white rounded-[20px] overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2">
            <ImageIcon className="w-5 h-5 text-[#0B2545]" />
            <h3 className="font-semibold text-[#0B2545]">Payment Screenshot</h3>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs"
              onClick={() => window.open(fullUrl, "_blank")}
            >
              <ZoomIn className="w-3.5 h-3.5" /> Open Full Size
            </Button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-slate-200 transition-colors text-slate-500 hover:text-slate-700"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Image */}
        <div className="bg-slate-100 flex items-center justify-center min-h-[300px] max-h-[70vh] overflow-auto p-4">
          <img
            src={fullUrl}
            alt="Payment screenshot"
            className="max-w-full max-h-[65vh] object-contain rounded-lg shadow-md"
          />
        </div>
      </div>
    </div>
  );
}

export default function AdminApplicationsPage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [freeApplications, setFreeApplications] = useState<CourseApplication[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [actioningId, setActioningId] = useState<string | null>(null);
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    setIsLoading(true);
    try {
      const [paymentsData, applicationsData] = await Promise.all([
        apiClient<Payment[]>("/subscriptions/payments/"),
        apiClient<{ results: CourseApplication[] }>("/admin/course-applications/"),
      ]);
      setPayments((paymentsData as any).results || paymentsData || []);
      setFreeApplications((applicationsData.results || []).filter((a) => !a.payment));
    } catch (error) {
      console.error("Error fetching applications:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePaymentApprove = async (id: number) => {
    setActioningId(`payment-${id}`);
    try {
      await apiClient(`/subscriptions/payments/${id}/approve/`, { method: "POST" });
      await fetchAll();
    } catch (error) {
      console.error("Failed to approve payment", error);
      alert("Failed to approve payment");
    } finally {
      setActioningId(null);
    }
  };

  const handlePaymentReject = async (id: number) => {
    if (!rejectReason.trim()) {
      alert("Please enter a rejection reason.");
      return;
    }
    setActioningId(`payment-${id}`);
    try {
      await apiClient(`/subscriptions/payments/${id}/reject/`, {
        method: "POST",
        body: JSON.stringify({ reason: rejectReason }),
      });
      setRejectingId(null);
      setRejectReason("");
      await fetchAll();
    } catch (error) {
      console.error("Failed to reject payment", error);
      alert("Failed to reject payment");
    } finally {
      setActioningId(null);
    }
  };

  const handleApplicationAction = async (id: number, action: "approved" | "rejected") => {
    setActioningId(`application-${id}`);
    try {
      await apiClient(`/admin/course-applications/${id}/`, {
        method: "PATCH",
        body: JSON.stringify({ status: action }),
      });
      await fetchAll();
    } catch (error) {
      console.error(`Failed to ${action} application`, error);
      alert(`Failed to update application`);
    } finally {
      setActioningId(null);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case "PENDING":
        return <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100 border-none"><Clock className="w-3 h-3 mr-1" /> Pending</Badge>;
      case "APPROVED":
        return <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 border-none"><CheckCircle2 className="w-3 h-3 mr-1" /> Approved</Badge>;
      case "REJECTED":
        return <Badge className="bg-red-100 text-red-700 hover:bg-red-100 border-none"><XCircle className="w-3 h-3 mr-1" /> Rejected</Badge>;
      default:
        return <Badge>{status}</Badge>;
    }
  };

  const rows: Row[] = [
    ...payments.map((p): Row => ({ kind: "payment", id: p.id, data: p })),
    ...freeApplications.map((a): Row => ({ kind: "free_application", id: a.id, data: a })),
  ].sort((a, b) => {
    const dateA = a.kind === "payment" ? a.data.submitted_at : a.data.applied_at;
    const dateB = b.kind === "payment" ? b.data.submitted_at : b.data.applied_at;
    return new Date(dateB).getTime() - new Date(dateA).getTime();
  });

  const pendingCount = payments.filter((p) => p.status === "PENDING").length + freeApplications.filter((a) => a.application_status === "pending").length;
  const approvedCount = payments.filter((p) => p.status === "APPROVED").length + freeApplications.filter((a) => a.application_status === "approved").length;
  const totalRevenue = payments.filter((p) => p.status === "APPROVED").reduce((acc, p) => acc + parseFloat(p.amount), 0);

  return (
    <div className="p-8 space-y-6">
      {/* Lightbox */}
      {lightboxSrc && (
        <ScreenshotLightbox src={lightboxSrc} onClose={() => setLightboxSrc(null)} />
      )}

      {/* Reject Modal */}
      {rejectingId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white rounded-[20px] shadow-2xl p-6 w-full max-w-md space-y-4">
            <h3 className="text-lg font-bold text-[#0B2545]">Reject Payment</h3>
            <p className="text-sm text-slate-500">Provide a reason so the student knows what to fix.</p>
            <textarea
              className="w-full border border-slate-200 rounded-xl p-3 text-sm resize-none min-h-[100px] focus:outline-none focus:ring-2 focus:ring-red-300"
              placeholder="e.g. Screenshot is blurry or transaction ID doesn't match..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
            <div className="flex justify-end gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setRejectingId(null); setRejectReason(""); }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={actioningId === `payment-${rejectingId}`}
                onClick={() => handlePaymentReject(rejectingId)}
                className="bg-red-600 hover:bg-red-700 text-white"
              >
                Confirm Reject
              </Button>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-[#0B2545]">Student Applications</h1>
          <p className="text-slate-500 mt-1">Review and approve student course applications and subscriptions</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white p-5 rounded-[16px] border border-slate-200 shadow-sm flex flex-col justify-center">
          <p className="text-sm font-medium text-slate-500">Total Requests</p>
          {isLoading ? <Skeleton className="mt-1 h-8 w-16" /> : <p className="text-2xl font-bold text-[#0B2545]">{rows.length}</p>}
        </div>
        <div className="bg-white p-5 rounded-[16px] border border-amber-200 shadow-sm flex flex-col justify-center bg-amber-50/30">
          <p className="text-sm font-medium text-amber-600">Pending</p>
          {isLoading ? <Skeleton className="mt-1 h-8 w-16" /> : <p className="text-2xl font-bold text-amber-700">{pendingCount}</p>}
        </div>
        <div className="bg-white p-5 rounded-[16px] border border-emerald-200 shadow-sm flex flex-col justify-center bg-emerald-50/30">
          <p className="text-sm font-medium text-emerald-600">Approved</p>
          {isLoading ? <Skeleton className="mt-1 h-8 w-16" /> : <p className="text-2xl font-bold text-emerald-700">{approvedCount}</p>}
        </div>
        <div className="bg-[#0B2545] p-5 rounded-[16px] border border-[#163E6B] shadow-sm flex flex-col justify-center text-white">
          <p className="text-sm font-medium text-slate-300">Total Revenue</p>
          {isLoading ? <Skeleton className="mt-1 h-8 w-28 bg-white/15" /> : <p className="text-2xl font-bold text-[#D4A72C]">Rs. {totalRevenue.toLocaleString()}</p>}
        </div>
      </div>

      <div className="bg-white rounded-[16px] border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full" aria-busy={isLoading}>
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-left text-sm font-medium text-slate-500">
                <th className="px-6 py-4">Student</th>
                <th className="px-6 py-4">Course / Plan</th>
                <th className="px-6 py-4">Amount</th>
                <th className="px-6 py-4">Method / TXN ID</th>
                <th className="px-6 py-4">Proof</th>
                <th className="px-6 py-4">Date</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {isLoading ? (
                Array.from({ length: 5 }, (_, rowIndex) => (
                  <tr key={`loading-${rowIndex}`} aria-hidden="true">
                    <td className="px-6 py-5"><Skeleton className="h-4 w-28" />{rowIndex === 0 && <span role="status" aria-live="polite" className="sr-only">Loading applications</span>}</td>
                    <td className="px-6 py-5"><Skeleton className="h-4 w-32" /></td>
                    <td className="px-6 py-5"><Skeleton className="h-4 w-16" /></td>
                    <td className="px-6 py-5"><Skeleton className="h-4 w-28" /></td>
                    <td className="px-6 py-5"><Skeleton className="h-10 w-10" /></td>
                    <td className="px-6 py-5"><Skeleton className="h-4 w-20" /></td>
                    <td className="px-6 py-5"><Skeleton className="h-5 w-16 rounded-full" /></td>
                    <td className="px-6 py-5"><Skeleton className="ml-auto h-8 w-24" /></td>
                  </tr>
                ))
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-slate-500">
                    No applications found.
                  </td>
                </tr>
              ) : (
                rows.map((row) => {
                  if (row.kind === "payment") {
                    const payment = row.data;
                    const isActioning = actioningId === `payment-${payment.id}`;
                    const screenshotUrl = payment.screenshot
                      ? (payment.screenshot.startsWith("http") ? payment.screenshot : `${API_BASE}${payment.screenshot}`)
                      : null;

                    return (
                      <tr key={`payment-${payment.id}`} className="hover:bg-slate-50/50 transition-colors">
                        <td className="px-6 py-4 font-medium text-[#0B2545]">{payment.student_name || "Unknown Student"}</td>
                        <td className="px-6 py-4 text-slate-600">
                          <p className="font-medium text-[#D4A72C]">{payment.plan_details?.name}</p>
                          <p className="text-xs text-slate-400 mb-2">{payment.plan_details?.duration} {payment.plan_details?.duration_unit}</p>
                          {payment.selected_courses && payment.selected_courses.length > 0 && (
                            <div className="space-y-1 mt-1 border-t border-slate-100 pt-1">
                              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Preparations:</p>
                              {payment.selected_courses.map(course => (
                                <p key={course.id} className="text-xs font-medium flex items-center gap-1"><CheckCircle2 className="w-3 h-3 text-[#22c55e]" /> {course.title}</p>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-4 text-[#0B2545] font-semibold">Rs. {payment.amount}</td>
                        <td className="px-6 py-4">
                          <p className="font-medium text-slate-600">{payment.payment_method_details?.display_name || "N/A"}</p>
                          <p className="text-xs font-mono text-slate-400">{payment.transaction_id}</p>
                          {payment.note && (
                            <p className="text-xs text-slate-400 mt-0.5 italic">Note: {payment.note}</p>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          {screenshotUrl ? (
                            <button
                              onClick={() => setLightboxSrc(screenshotUrl)}
                              className="group relative overflow-hidden rounded-lg border border-slate-200 hover:border-[#0B2545] transition-all shadow-sm"
                            >
                              <img
                                src={screenshotUrl}
                                alt="Payment proof"
                                className="w-14 h-14 object-cover group-hover:opacity-80 transition-opacity"
                              />
                              <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 bg-black/40 transition-opacity">
                                <Eye className="w-4 h-4 text-white" />
                              </div>
                            </button>
                          ) : (
                            <span className="text-xs text-slate-300 flex items-center gap-1">
                              <ImageIcon className="w-3.5 h-3.5" /> No proof
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-slate-500">
                          {new Date(payment.submitted_at).toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4">{getStatusBadge(payment.status)}</td>
                        <td className="px-6 py-4 text-right">
                          {payment.status === "PENDING" ? (
                            <div className="flex justify-end gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={isActioning}
                                onClick={() => setRejectingId(payment.id)}
                                className="border-red-200 text-red-600 hover:bg-red-50"
                              >
                                Reject
                              </Button>
                              <Button
                                variant="default"
                                size="sm"
                                disabled={isActioning}
                                onClick={() => handlePaymentApprove(payment.id)}
                                className="bg-emerald-600 hover:bg-emerald-700 text-white"
                              >
                                {isActioning ? "..." : "Approve"}
                              </Button>
                            </div>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              className="gap-1.5 border-slate-200"
                              onClick={() => screenshotUrl && setLightboxSrc(screenshotUrl)}
                              disabled={!screenshotUrl}
                            >
                              <Eye className="h-3.5 w-3.5" /> View
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  }

                  const app = row.data;
                  const isActioning = actioningId === `application-${app.id}`;
                  return (
                    <tr key={`application-${app.id}`} className="hover:bg-slate-50/50 transition-colors">
                      <td className="px-6 py-4 font-medium text-[#0B2545]">{app.student.name || app.student.username}</td>
                      <td className="px-6 py-4 text-slate-600">
                        <p className="font-medium">{app.course.title}</p>
                        <p className="text-xs text-slate-400 flex items-center gap-1"><Gift className="w-3 h-3" /> Free / Direct application</p>
                      </td>
                      <td className="px-6 py-4 text-slate-400">—</td>
                      <td className="px-6 py-4 text-slate-400">No payment required</td>
                      <td className="px-6 py-4 text-slate-300 text-xs flex items-center gap-1 mt-3">
                        <ImageIcon className="w-3.5 h-3.5" /> N/A
                      </td>
                      <td className="px-6 py-4 text-slate-500">
                        {new Date(app.applied_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4">{getStatusBadge(app.application_status)}</td>
                      <td className="px-6 py-4 text-right">
                        {app.application_status === "pending" ? (
                          <div className="flex justify-end gap-2">
                            <Button variant="outline" size="sm" disabled={isActioning} onClick={() => handleApplicationAction(app.id, "rejected")} className="border-red-200 text-red-600 hover:bg-red-50">
                              Reject
                            </Button>
                            <Button variant="default" size="sm" disabled={isActioning} onClick={() => handleApplicationAction(app.id, "approved")} className="bg-emerald-600 hover:bg-emerald-700 text-white">
                              {isActioning ? "..." : "Approve"}
                            </Button>
                          </div>
                        ) : (
                          <Button variant="outline" size="sm" className="gap-1.5 border-slate-200" disabled>
                            <Eye className="h-3.5 w-3.5" /> View
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
