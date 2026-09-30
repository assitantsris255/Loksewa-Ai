"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Inbox, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";
import { adminExamApi, AdminExaminationRequest } from "@/lib/api/admin-exams";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

function getErrorDetail(error: unknown, fallback: string) {
  if (typeof error !== "object" || error === null) return fallback;
  const data = "data" in error ? error.data : null;
  if (typeof data === "object" && data !== null && "detail" in data && typeof data.detail === "string") {
    return data.detail;
  }
  return fallback;
}

export default function ExaminationRequestsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<"all" | AdminExaminationRequest["status"]>("pending");
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const status = statusFilter === "all" ? undefined : statusFilter;
  const { data: requests = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["admin-exam-requests", statusFilter],
    queryFn: () => adminExamApi.getExamRequests(status),
  });

  const refresh = async () => queryClient.invalidateQueries({ queryKey: ["admin-exam-requests"] });

  const approve = async (requestId: number) => {
    setUpdatingId(requestId);
    try {
      await adminExamApi.approveExamRequest(requestId);
      toast.success("Exam request approved.");
      await refresh();
    } catch (error: unknown) {
      toast.error(getErrorDetail(error, "Could not approve exam request."));
    } finally {
      setUpdatingId(null);
    }
  };

  const reject = async (requestId: number) => {
    const rejection_reason = (reasons[requestId] || "").trim();
    if (!rejection_reason) return;
    setUpdatingId(requestId);
    try {
      await adminExamApi.rejectExamRequest(requestId, rejection_reason);
      toast.success("Exam request rejected.");
      setReasons((previous) => ({ ...previous, [requestId]: "" }));
      await refresh();
    } catch (error: unknown) {
      toast.error(getErrorDetail(error, "Could not reject exam request."));
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <main className="mx-auto max-w-6xl space-y-6 p-4 md:p-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm text-muted-foreground"><Inbox className="h-4 w-4" /> Examinations</div>
          <h1 className="text-2xl font-bold text-primary dark:text-foreground">Student Exam Requests</h1>
        </div>
        <label className="flex items-center gap-2 text-sm font-medium">
          Status
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
            className="h-9 rounded-md border border-input bg-background px-3"
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="all">All</option>
          </select>
        </label>
      </header>

      {isLoading ? (
        <p className="py-10 text-center text-sm text-muted-foreground" aria-live="polite">Loading requests...</p>
      ) : isError ? (
        <div className="flex items-center justify-center gap-3 border-y border-destructive/30 py-8 text-sm" role="alert">
          <span>Could not load exam requests.</span>
          <Button variant="outline" size="sm" onClick={() => void refetch()}><RotateCcw className="mr-2 h-4 w-4" />Retry</Button>
        </div>
      ) : requests.length === 0 ? (
        <p className="border-y border-border py-12 text-center text-sm text-muted-foreground">No {statusFilter === "all" ? "exam" : statusFilter} requests.</p>
      ) : (
        <div className="divide-y divide-border border-y border-border">
          {requests.map((request) => (
            <article key={request.id} className="grid gap-4 py-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="font-semibold text-primary dark:text-foreground">{request.examination_title}</h2>
                  <Badge variant={request.status === "approved" ? "default" : request.status === "rejected" ? "destructive" : "outline"}>
                    {request.status}
                  </Badge>
                  {request.request_type === "subjective_live" && <Badge variant="secondary">Subjective Live</Badge>}
                </div>
                <p className="text-sm text-muted-foreground">{request.student_name} · Requested {new Date(request.created_at).toLocaleString()}</p>
                {request.request_type === "subjective_live" && (
                  <p className="text-sm text-muted-foreground">
                    {[request.requested_exam_name, request.requested_course_title, request.requested_subject_name, request.requested_topic_name].filter(Boolean).join(" · ")}
                  </p>
                )}
                {request.rejection_reason && <p className="text-sm text-muted-foreground">Reason: {request.rejection_reason}</p>}
              </div>
              {request.status === "pending" && (
                <div className="flex flex-wrap items-center gap-2">
                  {request.request_type === "subjective_live" && !request.examination ? (
                    <>
                      <Link href={`/admin-dashboard/exams/subjective-generator?request=${request.id}`}>
                        <Button size="sm"><Inbox className="mr-2 h-4 w-4" />Generate Automatically</Button>
                      </Link>
                      <Link href={`/admin-dashboard/exams/new?subjectiveRequest=${request.id}`}>
                        <Button variant="outline" size="sm">Prepare Manually</Button>
                      </Link>
                    </>
                  ) : request.request_type === "subjective_live" && request.examination_status !== "published" ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="max-w-56 text-sm text-muted-foreground">Draft linked. Review and publish it to approve this request.</p>
                      {request.examination && (
                        <Link href={`/admin-dashboard/exams/new?draft=${request.examination}`}>
                          <Button variant="outline" size="sm">Review Draft</Button>
                        </Link>
                      )}
                    </div>
                  ) : (
                    <Button size="sm" disabled={updatingId !== null} onClick={() => void approve(request.id)}>
                      <Check className="mr-2 h-4 w-4" />Approve
                    </Button>
                  )}
                  <Input
                    aria-label={`Rejection reason for ${request.examination_title}`}
                    className="w-full md:w-64"
                    placeholder="Reason required to reject"
                    value={reasons[request.id] || ""}
                    onChange={(event) => setReasons((previous) => ({ ...previous, [request.id]: event.target.value }))}
                  />
                  <Button variant="outline" size="sm" disabled={!reasons[request.id]?.trim() || updatingId !== null} onClick={() => void reject(request.id)}>
                    <X className="mr-2 h-4 w-4" />Reject
                  </Button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </main>
  );
}