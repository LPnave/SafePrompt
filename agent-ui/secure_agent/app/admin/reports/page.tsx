"use client";

import { useEffect, useState } from "react";
import {
  adminApi,
  UsageSummaryItem,
  ThreatBreakdownItem,
  UserActivityItem,
  BlockedEventRecord,
} from "@/lib/admin-api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LineChart,
  Line,
  CartesianGrid,
  Legend,
} from "recharts";
import { Loader2, RefreshCw } from "lucide-react";

const COLORS = ["#3b82f6", "#ef4444", "#22c55e", "#f97316", "#a855f7", "#14b8a6"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border bg-card p-5 space-y-4">
      <p className="text-sm font-medium">{title}</p>
      {children}
    </div>
  );
}

export default function ReportsPage() {
  const [usage, setUsage] = useState<UsageSummaryItem[]>([]);
  const [threats, setThreats] = useState<ThreatBreakdownItem[]>([]);
  const [activity, setActivity] = useState<UserActivityItem[]>([]);
  const [blocked, setBlocked] = useState<BlockedEventRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    Promise.all([
      adminApi.reports.usage(),
      adminApi.reports.threats(),
      adminApi.reports.userActivity(),
      adminApi.reports.blocked(50),
    ])
      .then(([u, t, a, b]) => {
        setUsage(u);
        setThreats(t);
        setActivity(a);
        setBlocked(b);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  // Aggregate usage by day
  const byDay = Object.values(
    usage.reduce<Record<string, { day: string; total: number; blocked: number; sanitized: number }>>(
      (acc, r) => {
        if (!acc[r.day]) acc[r.day] = { day: r.day, total: 0, blocked: 0, sanitized: 0 };
        acc[r.day].total += r.total;
        acc[r.day].blocked += r.blocked;
        acc[r.day].sanitized += r.sanitized;
        return acc;
      },
      {}
    )
  )
    .sort((a, b) => a.day.localeCompare(b.day))
    .slice(-30);

  // Usage by role (pie)
  const byRole = Object.values(
    usage.reduce<Record<string, { role: string; total: number }>>((acc, r) => {
      if (!acc[r.role]) acc[r.role] = { role: r.role, total: 0 };
      acc[r.role].total += r.total;
      return acc;
    }, {})
  );

  // Threat actions pie
  const threatPie = Object.values(
    threats.reduce<Record<string, { name: string; value: number }>>((acc, t) => {
      if (!acc[t.action]) acc[t.action] = { name: t.action, value: 0 };
      acc[t.action].value += t.count;
      return acc;
    }, {})
  );

  const empty = (
    <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
      No data yet
    </div>
  );

  return (
    <div className="space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Prompt activity, security events, and user behaviour
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-accent transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Row 1 — Volume charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Section title="Prompt Volume (last 30 days)">
          <div className="lg:col-span-2">
            {loading ? (
              <div className="h-48 flex items-center justify-center"><Loader2 className="w-4 h-4 animate-spin" /></div>
            ) : byDay.length === 0 ? empty : (
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={byDay} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="total" stroke="#3b82f6" dot={false} name="Total" />
                  <Line type="monotone" dataKey="blocked" stroke="#ef4444" dot={false} name="Blocked" />
                  <Line type="monotone" dataKey="sanitized" stroke="#f97316" dot={false} name="Sanitized" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Section>

        <Section title="Volume by Role">
          {loading ? (
            <div className="h-48 flex items-center justify-center"><Loader2 className="w-4 h-4 animate-spin" /></div>
          ) : byRole.length === 0 ? empty : (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={byRole} dataKey="total" nameKey="role" cx="50%" cy="50%" outerRadius={65} label={({ role }) => role} labelLine={false}>
                  {byRole.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Section>
      </div>

      {/* Row 2 — Threats + User activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="Security Actions">
          {loading ? (
            <div className="h-48 flex items-center justify-center"><Loader2 className="w-4 h-4 animate-spin" /></div>
          ) : threatPie.length === 0 ? empty : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={threatPie} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" name="Count" radius={[4, 4, 0, 0]}>
                  {threatPie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Section>

        <Section title="User Activity Summary">
          {loading ? (
            <div className="h-48 flex items-center justify-center"><Loader2 className="w-4 h-4 animate-spin" /></div>
          ) : activity.length === 0 ? empty : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b">
                    {["User ID", "Role", "Dept", "Prompts", "Blocked", "Avg Latency"].map((h) => (
                      <th key={h} className="pb-2 text-left font-medium text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {activity.slice(0, 10).map((row, i) => (
                    <tr key={i} className="hover:bg-muted/30">
                      <td className="py-1.5">{row.user_id ?? "—"}</td>
                      <td className="py-1.5 capitalize">{row.role ?? "—"}</td>
                      <td className="py-1.5 text-muted-foreground">{row.department ?? "—"}</td>
                      <td className="py-1.5 font-medium">{row.total_prompts}</td>
                      <td className="py-1.5 text-red-500">{row.blocked}</td>
                      <td className="py-1.5 text-muted-foreground">{row.avg_latency_ms}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      {/* Row 3 — Blocked events */}
      <Section title="Recent Blocked Prompts">
        {loading ? (
          <div className="h-24 flex items-center justify-center"><Loader2 className="w-4 h-4 animate-spin" /></div>
        ) : blocked.length === 0 ? (
          <p className="text-sm text-muted-foreground">No blocked prompts yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b">
                  {["Timestamp", "User ID", "Role", "Dept", "Length", "Threats", "Reason", "Security Level"].map((h) => (
                    <th key={h} className="pb-2 pr-4 text-left font-medium text-muted-foreground whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y">
                {blocked.map((ev) => (
                  <tr key={ev.id} className="hover:bg-muted/30">
                    <td className="py-1.5 pr-4 whitespace-nowrap text-muted-foreground">
                      {new Date(ev.timestamp).toLocaleString()}
                    </td>
                    <td className="py-1.5 pr-4">{ev.user_id ?? "—"}</td>
                    <td className="py-1.5 pr-4 capitalize">{ev.user_role ?? "—"}</td>
                    <td className="py-1.5 pr-4">{ev.department ?? "—"}</td>
                    <td className="py-1.5 pr-4">{ev.prompt_length}</td>
                    <td className="py-1.5 pr-4">
                      {ev.threats_detected?.join(", ") ?? "—"}
                    </td>
                    <td className="py-1.5 pr-4 text-destructive">{ev.block_reason ?? "—"}</td>
                    <td className="py-1.5 pr-4">
                      <span className="rounded-full bg-muted px-2 py-0.5">
                        {ev.security_level_used ?? "—"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}
