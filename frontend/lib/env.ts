/**
 * Centralised, runtime-validated environment.
 *
 * All `NEXT_PUBLIC_*` vars are inlined by Next at build time, so this file is
 * safe to import from both server and client.  When backend services are not
 * yet provisioned (default for local dev and the Phase 5 PR demo), the mock
 * simulator is enabled automatically.
 */

import { z } from "zod";

const Schema = z.object({
  NEXT_PUBLIC_API_BASE: z.string().url().optional(),
  NEXT_PUBLIC_WS_BASE: z.string().url().optional(),
  NEXT_PUBLIC_LIVEKIT_URL: z.string().url().optional(),
  NEXT_PUBLIC_USE_MOCKS: z
    .union([z.literal("0"), z.literal("1"), z.literal("true"), z.literal("false")])
    .optional(),
  NEXT_PUBLIC_APP_NAME: z.string().optional(),
});

const raw = Schema.parse({
  NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE,
  NEXT_PUBLIC_WS_BASE: process.env.NEXT_PUBLIC_WS_BASE,
  NEXT_PUBLIC_LIVEKIT_URL: process.env.NEXT_PUBLIC_LIVEKIT_URL,
  NEXT_PUBLIC_USE_MOCKS: process.env.NEXT_PUBLIC_USE_MOCKS,
  NEXT_PUBLIC_APP_NAME: process.env.NEXT_PUBLIC_APP_NAME,
});

const explicitMock =
  raw.NEXT_PUBLIC_USE_MOCKS === "1" || raw.NEXT_PUBLIC_USE_MOCKS === "true";
const explicitReal =
  raw.NEXT_PUBLIC_USE_MOCKS === "0" || raw.NEXT_PUBLIC_USE_MOCKS === "false";

const apiBase = raw.NEXT_PUBLIC_API_BASE ?? "";
const wsBase =
  raw.NEXT_PUBLIC_WS_BASE ??
  (apiBase ? apiBase.replace(/^http/i, "ws") : "");

export const env = {
  apiBase,
  wsBase,
  livekitUrl: raw.NEXT_PUBLIC_LIVEKIT_URL ?? "",
  appName: raw.NEXT_PUBLIC_APP_NAME ?? "Dronan",
  // Mock when explicitly requested OR when no API base is configured.
  useMocks: explicitMock || (!explicitReal && !apiBase),
};

export default env;
