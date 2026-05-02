"use client";

import { useState } from "react";

import type { PingErrorDetail } from "@/lib/mongo-ping-error-detail";

type PingResult = {
  ok: boolean;
  error?: string;
  errorDetail?: PingErrorDetail;
  version?: string;
  databases?: string[];
  databasesNote?: string;
  httpStatus?: number;
};

function formatJson(block: unknown): string {
  try {
    return JSON.stringify(block, null, 2);
  } catch {
    return String(block);
  }
}

export default function AtlasPingPanel() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PingResult | null>(null);

  async function runTest() {
    setBusy(true);
    setResult(null);
    try {
      const response = await fetch("/api/mongo/ping", { cache: "no-store" });
      const raw = await response.text();
      let data: PingResult;
      try {
        data = JSON.parse(raw) as PingResult;
        if (!response.ok) data.httpStatus = response.status;
      } catch {
        data = {
          ok: false,
          httpStatus: response.status,
          error: `Response was not JSON (HTTP ${response.status} ${response.statusText})`,
          errorDetail: {
            kind: "ParseError",
            hints: [
              "The API returned non-JSON — check terminal logs while running next dev.",
              `First ${Math.min(raw.length, 800)} chars of body shown below.`,
            ],
            topology: raw.length <= 2500 ? raw : `${raw.slice(0, 2500)}\n…[truncated]`,
          },
        };
      }
      setResult(data);
    } catch (e) {
      setResult({
        ok: false,
        httpStatus: undefined,
        error: e instanceof Error ? e.message : String(e),
        errorDetail: {
          kind: "NetworkError",
          hints: ["Browser could not reach the Next server — confirm `npm run dev` is running for `frontend/`."],
        },
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-labelledby="atlas-ping-heading"
      className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-700 dark:bg-slate-900"
    >
      <div className="space-y-1">
        <h2 id="atlas-ping-heading" className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
          MongoDB Atlas
        </h2>
        <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400">
          Uses the Node <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-800">mongodb</code> driver in a Route Handler{" "}
          <span className="whitespace-nowrap">(<code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-800">GET /api/mongo/ping</code>) </span>.
          Credentials stay on the server.
        </p>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void runTest()}
          disabled={busy}
          aria-busy={busy}
          className="cursor-pointer rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:bg-sky-600 dark:text-white dark:hover:bg-sky-500"
        >
          {busy ? "Testing…" : "Run connection test"}
        </button>
      </div>

      {result && (
        <div
          role="region"
          aria-live="polite"
          className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-600 dark:bg-slate-950/40"
        >
          {typeof result.httpStatus === "number" && !result.ok && (
            <p className="mb-2 font-mono text-xs text-slate-500 dark:text-slate-400">
              HTTP {result.httpStatus}
            </p>
          )}
          {result.ok ? (
            <div className="space-y-2 text-slate-800 dark:text-slate-200">
              <p className="font-medium text-emerald-800 dark:text-emerald-300">Ping succeeded.</p>
              {result.version && (
                <p>
                  <span className="text-slate-500 dark:text-slate-400">Server version</span>{" "}
                  <span className="font-mono text-slate-900 dark:text-slate-100">{result.version}</span>
                </p>
              )}
              {result.databases && result.databases.length > 0 && (
                <div>
                  <p className="text-slate-500 dark:text-slate-400">Databases</p>
                  <ul className="mt-1 max-h-40 list-inside list-disc overflow-y-auto font-mono text-xs text-slate-800 dark:text-slate-200">
                    {result.databases.map((d) => (
                      <li key={d}>{d}</li>
                    ))}
                  </ul>
                </div>
              )}
              {result.databasesNote && (
                <p className="text-xs text-slate-600 dark:text-slate-400">{result.databasesNote}</p>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <p className="font-medium leading-snug text-red-800 dark:text-red-400">
                <span className="mr-2 text-red-950 dark:text-red-200">{result.errorDetail?.kind ?? "Error"}:</span>
                <span className="font-normal whitespace-pre-wrap break-words">{result.error ?? "Unknown error"}</span>
              </p>

              {result.errorDetail && (
                <>
                  {(result.errorDetail.code != null || result.errorDetail.codeName) && (
                    <dl className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs text-slate-700 dark:text-slate-300">
                      {result.errorDetail.code != null && (
                        <>
                          <dt className="text-slate-500 dark:text-slate-400">code</dt>
                          <dd>{String(result.errorDetail.code)}</dd>
                        </>
                      )}
                      {result.errorDetail.codeName != null && result.errorDetail.codeName.length > 0 && (
                        <>
                          <dt className="text-slate-500 dark:text-slate-400">codeName</dt>
                          <dd>{result.errorDetail.codeName}</dd>
                        </>
                      )}
                    </dl>
                  )}

                  {result.errorDetail.errorLabels != null && result.errorDetail.errorLabels.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Labels
                      </p>
                      <p className="mt-1 font-mono text-xs text-slate-800 dark:text-slate-200">
                        {result.errorDetail.errorLabels.join(", ")}
                      </p>
                    </div>
                  )}

                  {result.errorDetail.hints != null && result.errorDetail.hints.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Likely fixes
                      </p>
                      <ul className="mt-2 list-disc space-y-2 pl-5 text-xs leading-relaxed text-slate-700 dark:text-slate-300">
                        {result.errorDetail.hints.map((h) => (
                          <li key={h}>{h}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {result.errorDetail.causes != null && result.errorDetail.causes.length > 0 && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Cause chain
                      </p>
                      <ol className="mt-2 space-y-2 text-xs leading-relaxed text-slate-800 dark:text-slate-200">
                        {result.errorDetail.causes.map((c, i) => (
                          <li key={`${i}-${c.message.slice(0, 32)}`} className="list-decimal ml-5 pl-1">
                            <span className="font-mono text-slate-500 dark:text-slate-400">{c.name ?? "Error"}:</span>{" "}
                            <span className="whitespace-pre-wrap break-words">{c.message}</span>
                            {c.code != null && (
                              <span className="ml-2 font-mono text-slate-500">code={String(c.code)}</span>
                            )}
                            {c.codeName != null && <span className="ml-1 font-mono text-slate-500">{c.codeName}</span>}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {result.errorDetail.topology != null && (
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        Topology snapshot
                      </p>
                      <pre className="mt-2 max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-[11px] leading-snug text-slate-900 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100">
                        {typeof result.errorDetail.topology === "string"
                          ? result.errorDetail.topology
                          : formatJson(result.errorDetail.topology)}
                      </pre>
                    </div>
                  )}

                  {result.errorDetail.stack != null && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-slate-600 underline decoration-slate-400 underline-offset-2 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200">
                        Server stack trace (development / verbose)
                      </summary>
                      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-slate-200 bg-white p-3 font-mono text-[11px] text-slate-800 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-200">
                        {result.errorDetail.stack}
                      </pre>
                    </details>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
