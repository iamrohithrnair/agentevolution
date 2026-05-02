/**
 * Produce safe, detailed diagnostics for Mongo ping failures (no URIs/passwords).
 */

import type { MongoError as MongoDriverErrorLike } from "mongodb";
import { MongoServerError, MongoSystemError } from "mongodb";

const MAX_TOPOLOGY_JSON_CHARS = 24_000;

export type PingErrorCause = {
  name?: string;
  message: string;
  code?: number;
  codeName?: string;
};

export type PingErrorDetail = {
  kind: string;
  code?: number;
  codeName?: string;
  errorLabels?: string[];
  /** Driver topology snapshot when available (e.g. server selection timeouts). */
  topology?: unknown;
  /** Nested / underlying errors (truncated depth). */
  causes?: PingErrorCause[];
  /** Included when NODE_ENV=development or MONGO_PING_VERBOSE_ERRORS=1 */
  stack?: string;
  /** Actionable guesses — not authoritative. */
  hints?: string[];
};

function detailEnabled(): boolean {
  const v = (process.env.MONGO_PING_VERBOSE_ERRORS ?? "").toLowerCase();
  return process.env.NODE_ENV === "development" || v === "1" || v === "true" || v === "yes";
}

function collectMongoFields(err: Error): Partial<Omit<PingErrorDetail, "kind">> & Pick<PingErrorDetail, "kind"> {
  const mo = err as Error & MongoDriverErrorLike;
  const kind =
    typeof mo.name === "string" && mo.name.length > 0 ? mo.name : "Error";

  const out: Partial<Omit<PingErrorDetail, "kind">> & Pick<PingErrorDetail, "kind"> = { kind };

  if (typeof mo.code === "number") out.code = mo.code;
  if (Array.isArray(mo.errorLabels) && mo.errorLabels.length > 0) {
    out.errorLabels = [...mo.errorLabels];
  }
  return out;
}

function collectCauses(err: unknown): PingErrorCause[] {
  const raw: PingErrorCause[] = [];

  function walk(cur: unknown, depth: number) {
    if (depth > 6 || cur == null) return;

    if (typeof AggregateError !== "undefined" && cur instanceof AggregateError) {
      for (const sub of cur.errors) walk(sub, depth + 1);
      if (cur.cause != null) walk(cur.cause, depth + 1);
      return;
    }

    if (cur instanceof Error) {
      const row: PingErrorCause = {
        name: cur.name,
        message: cur.message,
      };
      const code = (cur as { code?: unknown }).code;
      if (typeof code === "number") row.code = code;
      const codeName = (cur as { codeName?: unknown }).codeName;
      if (typeof codeName === "string") row.codeName = codeName;
      const msg = row.message.trim();
      if (msg) raw.push(row);
      const c = cur.cause;
      if (c != null) walk(c, depth + 1);
    }
  }

  walk(err, 0);
  return Array.from(new Map(raw.map((c) => [`${c.name ?? ""}:${c.code ?? ""}:${c.message}`, c])).values()).slice(
    0,
    14,
  );
}

function topologyFromMongoError(err: Error): unknown | undefined {
  try {
    if (!(err instanceof MongoSystemError)) return undefined;
    const reason = err.reason;
    if (reason != null && typeof reason.toJSON === "function") {
      return reason.toJSON();
    }
  } catch {
    return undefined;
  }
  return undefined;
}

/** Returns JSON-serializable value; oversized topology becomes a truncation wrapper. */
function safeTopology(payload: unknown): unknown {
  try {
    const s = JSON.stringify(payload);
    if (s.length <= MAX_TOPOLOGY_JSON_CHARS) return JSON.parse(s);
    return {
      truncated: true,
      topologyBytes: s.length,
      topologyPreviewChars: MAX_TOPOLOGY_JSON_CHARS,
      previewText: `${s.slice(0, MAX_TOPOLOGY_JSON_CHARS)}…`,
    };
  } catch {
    return undefined;
  }
}

function hintsFor(detail: PingErrorDetail, message: string): string[] {
  const hints = new Set<string>();
  let blob = message.toLowerCase();
  try {
    blob +=
      typeof detail.topology === "object" && detail.topology !== null
        ? JSON.stringify(detail.topology).toLowerCase()
        : ` ${typeof detail.topology === "string" ? detail.topology.toLowerCase() : ""}`;
  } catch {
    /* ignore stringification failures */
  }

  if (blob.includes("replicasetnoprimary") || blob.includes("replica_set_no_primary")) {
    hints.add(
      'Topology stuck with no primary usually means replicas never become selectable — TCP/TLS to shards failed (Atlas IP allowlist vs your outbound IP, firewall on 27017, VPN egress, TLS trust/MITM bundle).',
    );
  }

  if (blob.includes('"type":"unknown') || /\btimeout\b/i.test(blob)) {
    hints.add(
      'Long “Unknown” members or timeouts: confirm Network Access lists the IP Atlas actually sees from this laptop; corporate inspection needs MONGODB_TLS_CA_FILE aligned with pymongo/Python.',
    );
  }

  const low = message.toLowerCase();
  if (low.includes("authenticationfailed") || low.includes("authentication failed")) {
    hints.add(
      'Auth failures: reset DB user password in Atlas; encode special chars in URI; set authSource if the user belongs to admin only.',
    );
  }

  if (/tls|ssl|certificate|cert verify|eof/i.test(message)) {
    hints.add(
      'TLS/cert: load the PEM chain your HTTPS stack trusts (combined-cert-bundle); avoid MONGODB_TLS_ALLOW_INVALID except local debugging.',
    );
  }

  return [...hints];
}

export function serializeMongoPingFailure(err: unknown): { summary: string; detail: PingErrorDetail } {
  const baseMessage =
    err instanceof Error ? err.message : typeof err === "string" ? err : JSON.stringify(err);
  const summary = baseMessage.trim() || "Unknown error";

  const errObj = err instanceof Error ? err : new Error(summary);
  const detail: PingErrorDetail = {
    ...collectMongoFields(errObj),
  };

  if (err instanceof MongoServerError) {
    detail.codeName = err.codeName;
  }

  detail.causes = collectCauses(err);

  if (err instanceof Error) {
    const top = topologyFromMongoError(err);
    if (top !== undefined) detail.topology = safeTopology(top);
    if (detailEnabled()) detail.stack = err.stack;
  }

  detail.hints = hintsFor(detail, summary);

  return { summary, detail };
}
