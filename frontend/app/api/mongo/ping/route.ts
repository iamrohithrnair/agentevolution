import { MongoClient } from "mongodb";
import { NextResponse } from "next/server";

import { getMongoUri, mongoClientOptions } from "@/lib/mongo-atlas-env";
import { type PingErrorDetail, serializeMongoPingFailure } from "@/lib/mongo-ping-error-detail";

export const dynamic = "force-dynamic";

type PingPayload = {
  ok: boolean;
  error?: string;
  errorDetail?: PingErrorDetail;
  version?: string;
  databases?: string[];
  databasesNote?: string;
};

export async function GET() {
  const uri = getMongoUri();
  if (!uri) {
    const detail: PingErrorDetail = {
      kind: "ConfigurationError",
      hints: [
        "Create repo-root `.env` with `MONGODB_URI=...`, or override in `frontend/.env.local`. Never use NEXT_PUBLIC_* for database credentials.",
        "This route runs only on the server; the React bundle never receives the URI.",
      ],
    };
    return NextResponse.json<PingPayload>(
      {
        ok: false,
        error:
          "Missing MongoDB URI — set `MONGODB_URI` (or `MONGODB_ATLAS_URI` / `ATLAS_CONNECTION_STRING`).",
        errorDetail: detail,
      },
      { status: 400 },
    );
  }

  let client: MongoClient | undefined;

  try {
    client = new MongoClient(uri, mongoClientOptions());
    await client.connect();
    await client.db("admin").command({ ping: 1 });

    let version: string | undefined;
    try {
      const bi = await client.db("admin").command({ buildInfo: 1 });
      if (bi && typeof bi === "object" && "version" in bi && typeof (bi as { version: unknown }).version === "string") {
        version = (bi as { version: string }).version;
      }
    } catch {
      /* buildInfo optional */
    }

    let databases: string[] | undefined;
    let databasesNote: string | undefined;
    try {
      const ld = await client.db("admin").admin().listDatabases({ nameOnly: true });
      databases = ld.databases
        .map((d: { name: string }) => d.name)
        .sort((a: string, b: string) => a.localeCompare(b));
    } catch {
      databasesNote =
        "Could not list databases (permissions may disallow listDatabases); ping succeeded.";
    }

    const body: PingPayload = {
      ok: true,
      version,
      databases: databases?.slice(0, 40),
      databasesNote:
        databases && databases.length > 40
          ? `Showing first 40 of ${databases.length} databases.`
          : databasesNote,
    };

    return NextResponse.json(body);
  } catch (e) {
    const { summary, detail } = serializeMongoPingFailure(e);
    const body: PingPayload = {
      ok: false,
      error: summary,
      errorDetail: detail,
    };
    return NextResponse.json(body, { status: 502 });
  } finally {
    await client?.close();
  }
}
