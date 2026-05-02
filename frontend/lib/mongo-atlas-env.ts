import fs from "node:fs";
import path from "node:path";
import { homedir } from "node:os";
import { config } from "dotenv";
import type { MongoClientOptions } from "mongodb";

config({ path: path.resolve(process.cwd(), "..", ".env") });
config({ path: path.resolve(process.cwd(), ".env.local") });

function stripWrappingQuotes(raw: string): string {
  let s = raw.trim();
  let changed = true;
  while (changed) {
    changed = false;
    for (const q of [`"`, "'", "`"]) {
      if (s.startsWith(q) && s.endsWith(q) && s.length >= 2) {
        s = s.slice(1, -1).trim();
        changed = true;
      }
    }
  }
  return s;
}

function expandVars(raw: string): string {
  return raw
    .replace(/\$\{(\w+)\}/g, (_, k: string) => process.env[k] ?? "")
    .replace(/\$(\w+)/g, (_, k: string) => process.env[k] ?? "");
}

export function resolveEnvPath(raw: string): string {
  let p = stripWrappingQuotes(raw);
  p = expandVars(p).trim();

  if (p === "~") {
    p = homedir();
  } else if (p.startsWith("~/")) {
    p = path.join(homedir(), p.slice(2));
  } else {
    const tiltHome = "~" + path.sep;
    if (p.startsWith(tiltHome)) {
      p = path.join(homedir(), p.slice(tiltHome.length));
    }
  }

  return path.resolve(p);
}

function envTruthy(raw: string | undefined): boolean {
  const v = (raw ?? "").trim().toLowerCase();
  return v === "1" || v === "true" || v === "yes" || v === "on";
}

export function mongoClientOptions(): MongoClientOptions {
  const opts: MongoClientOptions = {
    serverSelectionTimeoutMS: 15_000,
    appName: "agentevolution-next-ping",
  };

  if (
    envTruthy(process.env.MONGODB_TLS_ALLOW_INVALID) ||
    envTruthy(process.env.MONGODB_TLS_INSECURE)
  ) {
    console.warn("[mongo-atlas-env] tlsAllowInvalidCertificates enabled (development only)");
    opts.tlsAllowInvalidCertificates = true;
    return opts;
  }

  const caRaw =
    process.env.MONGODB_TLS_CA_FILE ||
    process.env.MONGO_TLS_CA_FILE ||
    process.env.SSL_CERT_FILE;

  if (caRaw) {
    const caPath = resolveEnvPath(caRaw);
    if (fs.existsSync(caPath)) {
      opts.tlsCAFile = caPath;
    } else {
      console.warn(`[mongo-atlas-env] TLS CA bundle missing or unreadable: ${caPath}`);
    }
  }

  return opts;
}

export function getMongoUri(): string | undefined {
  const uri =
    process.env.MONGODB_URI ??
    process.env.MONGODB_ATLAS_URI ??
    process.env.ATLAS_CONNECTION_STRING;
  return uri?.trim() || undefined;
}
