"use client";

import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import env from "@/lib/env";

export default function SettingsPage() {
  const [voiceMode, setVoiceMode] = useState<"ptt" | "always_on">("always_on");
  const [language, setLanguage] = useState<"en" | "auto">("en");
  const [terseNarration, setTerseNarration] = useState(false);
  const [riskAbort, setRiskAbort] = useState(true);

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Operator preferences. Changes embed into mission_memory as
          <code className="mx-1 rounded bg-[var(--color-surface-2)] px-1 py-0.5 text-[11px]">
            operator_pref
          </code>
          and influence future planner runs.
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Voice console</CardTitle>
            <CardDescription>How Mission Control speaks to and listens to you.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <Row label="Mode">
              <Select
                value={voiceMode}
                onValueChange={(v) => setVoiceMode(v as "ptt" | "always_on")}
              >
                <SelectTrigger className="w-44" aria-label="Voice mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="always_on">Always-on</SelectItem>
                  <SelectItem value="ptt">Push-to-talk</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Language">
              <Select value={language} onValueChange={(v) => setLanguage(v as "en" | "auto")}>
                <SelectTrigger className="w-44" aria-label="Language">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="auto">Auto-detect</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Terse narration">
              <Switch checked={terseNarration} onCheckedChange={setTerseNarration} aria-label="Terse narration" />
            </Row>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Mission policy</CardTitle>
            <CardDescription>Defaults for the planner cascade.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <Row label="Auto-abort on risk ≥ 70">
              <Switch checked={riskAbort} onCheckedChange={setRiskAbort} aria-label="Auto-abort" />
            </Row>
            <Row label="Default origin">
              <Badge variant="outline">fac_depot_canary</Badge>
            </Row>
            <Row label="Default priority">
              <Badge variant="accent">high</Badge>
            </Row>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Environment</CardTitle>
            <CardDescription>What this build is talking to.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-2 text-xs sm:grid-cols-2">
              <Stat label="App" value={env.appName} />
              <Stat label="Mode" value={env.useMocks ? "mock backend" : "live backend"} />
              <Stat label="API base" value={env.apiBase || "—"} />
              <Stat label="WS base" value={env.wsBase || "—"} />
              <Stat label="LiveKit URL" value={env.livekitUrl || "—"} />
            </dl>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
      <span className="text-[var(--color-fg-muted)]">{label}</span>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2">
      <dt className="text-[var(--color-fg-muted)]">{label}</dt>
      <dd className="font-mono text-[var(--color-fg)]">{value}</dd>
    </div>
  );
}
