"use client";

import { useEffect, useState, useCallback } from "react";
import { Loader2, AlertCircle, FileQuestion, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getPublicWebsitePage, type WebsitePageResult } from "@/lib/api/website-pages";
import { LegalContent } from "./LegalContent";

/**
 * Shared shell for every admin-managed public page (/contact, /privacy,
 * /terms, /refund) - one implementation, driven by slug, instead of four
 * near-identical page components. Renders exactly one of: loading, the
 * real published content, "not published yet", or an error + retry -
 * never a hardcoded fallback.
 */
export function PublicLegalPage({ slug }: { slug: string }) {
  const [result, setResult] = useState<WebsitePageResult | null>(null);

  const load = useCallback(() => {
    setResult(null);
    getPublicWebsitePage(slug).then(setResult);
  }, [slug]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-[#0A1118]">
      <main className="flex-grow pt-32 pb-24">
        <div className="container mx-auto px-4 max-w-[760px]">
          {result === null && (
            <div className="flex flex-col items-center justify-center py-24 gap-3 text-slate-500 dark:text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin" />
              <p className="text-sm">Loading…</p>
            </div>
          )}

          {result?.status === "not_published" && (
            <div className="flex flex-col items-center text-center py-24 gap-4">
              <div className="w-14 h-14 rounded-full bg-slate-100 dark:bg-white/5 flex items-center justify-center">
                <FileQuestion className="w-6 h-6 text-slate-400 dark:text-slate-500" />
              </div>
              <p className="text-slate-600 dark:text-slate-300 font-medium">This page has not been published yet.</p>
              <p className="text-sm text-slate-400 dark:text-slate-500 max-w-sm">Please check back later, or contact us if you need this information right away.</p>
            </div>
          )}

          {result?.status === "error" && (
            <div className="flex flex-col items-center text-center py-24 gap-4">
              <div className="w-14 h-14 rounded-full bg-red-50 dark:bg-red-500/10 flex items-center justify-center">
                <AlertCircle className="w-6 h-6 text-red-500" />
              </div>
              <p className="text-slate-700 dark:text-slate-200 font-medium">Couldn&apos;t load this page.</p>
              <p className="text-sm text-slate-400 dark:text-slate-500">{result.message}</p>
              <Button onClick={load} variant="outline" className="gap-2 mt-2">
                <RefreshCw className="w-3.5 h-3.5" /> Try again
              </Button>
            </div>
          )}

          {result?.status === "found" && (
            <article>
              <h1 className="text-3xl md:text-4xl font-[900] text-slate-900 dark:text-white mb-2">{result.page.title}</h1>
              <p className="text-xs text-slate-400 dark:text-slate-500 mb-10">
                Last updated {new Date(result.page.updated_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
              </p>
              <LegalContent content={result.page.content} />
            </article>
          )}
        </div>
      </main>
    </div>
  );
}
