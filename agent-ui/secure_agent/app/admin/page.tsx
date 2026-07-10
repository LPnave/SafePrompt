"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminApi, UsageSummaryItem, ThreatBreakdownItem } from "@/lib/admin-api";
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
} from "recharts";
import { Users, ShieldAlert, ShieldCheck, Activity, ArrowRight } from "lucide-react";

const THREAT_COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#3b82f6"];

function StatCard({
  label,
  value,
  icon: Icon,
  sub,
  href,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  sub?: string;
  href?: string;
}) {
  const inner = (
    <div className="flex h-full min-h-[9.5rem] flex-col rounded-xl border bg-card p-5 hover:shadow-sm transition">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{label}</p>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </div>
      <p className="mt-3 text-3xl font-semibold">{value}</p>
      <p
        className={`mt-1 min-h-4 text-xs text-muted-foreground ${sub ? "" : "invisible"}`}
        aria-hidden={!sub}
      >
        {sub ?? "\u00a0"}
      </p>
      {href && (
        <div className="mt-auto flex items-center gap-1 pt-3 text-xs text-primary">
          View details <ArrowRight className="w-3 h-3" />
        </div>
      )}
    </div>
  );
  return href ? (
    <Link href={href} className="block h-full">
      {inner}
    </Link>
  ) : (
    inner
  );
}

export default function AdminDashboard() {
  const [usage, setUsage] = useState<UsageSummaryItem[]>([]);
  const [threats, setThreats] = useState<ThreatBreakdownItem[]>([]);
  const [userCount, setUserCount] = useState<number | null>(null);
  const [activeUserCount, setActiveUserCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      adminApi.reports.usage(),
      adminApi.reports.threats(),
      adminApi.users.list(),
    ])
      .then(([u, t, users]) => {
        setUsage(u);
        setThreats(t);
        setUserCount(users.length);
        setActiveUserCount(users.filter((user) => user.is_active).length);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // Aggregate stats from usage data
  const totalPrompts = usage.reduce((s, r) => s + r.total, 0);
  const totalBlocked = usage.reduce((s, r) => s + r.blocked, 0);
  const totalSanitized = usage.reduce((s, r) => s + r.sanitized, 0);
  const blockRate = totalPrompts
    ? ((totalBlocked / totalPrompts) * 100).toFixed(1)
    : "0";

  // Aggregate usage by day for bar chart
  const byDay = Object.values(
    usage.reduce<Record<string, { day: string; total: number; blocked: number }>>(
      (acc, r) => {
        if (!acc[r.day]) acc[r.day] = { day: r.day, total: 0, blocked: 0 };
        acc[r.day].total += r.total;
        acc[r.day].blocked += r.blocked;
        return acc;
      },
      {}
    )
  )
    .sort((a, b) => a.day.localeCompare(b.day))
    .slice(-14); // last 14 days

  // Threat pie data
  const threatByAction = threats.reduce<Record<string, number>>((acc, t) => {
    acc[t.action] = (acc[t.action] || 0) + t.count;
    return acc;
  }, {});
  const pieData = Object.entries(threatByAction).map(([name, value]) => ({ name, value }));

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Overview of prompt activity and security events
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 items-stretch gap-4 lg:grid-cols-4">
        <StatCard label="Total Prompts" value={totalPrompts} icon={Activity} href="/admin/reports" />
        <StatCard
          label="Blocked"
          value={totalBlocked}
          icon={ShieldAlert}
          sub={`${blockRate}% block rate`}
          href="/admin/reports"
        />
        <StatCard label="Sanitized" value={totalSanitized} icon={ShieldCheck} href="/admin/reports" />
        <StatCard
          label="Manage Users"
          value={loading ? "—" : (userCount ?? 0)}
          icon={Users}
          sub={
            !loading && userCount !== null && activeUserCount !== null
              ? `${activeUserCount} active`
              : undefined
          }
          href="/admin/users"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Usage bar chart */}
        <div className="lg:col-span-2 rounded-xl border bg-card p-5 space-y-3">
          <p className="text-sm font-medium">Prompt Volume (last 14 days)</p>
          {loading ? (
            <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
              Loading…
            </div>
          ) : byDay.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
              No data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={byDay} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <XAxis
                  dataKey="day"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => v.slice(5)}
                />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="total" name="Total" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
                <Bar dataKey="blocked" name="Blocked" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Threat pie */}
        <div className="rounded-xl border bg-card p-5 space-y-3">
          <p className="text-sm font-medium">Actions Taken</p>
          {loading ? (
            <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
              Loading…
            </div>
          ) : pieData.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
              No data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  outerRadius={70}
                  dataKey="value"
                  label={({ name, percent }) =>
                    `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={THREAT_COLORS[i % THREAT_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Quick links */}
      <div className="flex gap-3 flex-wrap">
        <Link
          href="/admin/users"
          className="rounded-lg border px-4 py-2 text-sm hover:bg-accent transition flex items-center gap-2"
        >
          <Users className="w-4 h-4" /> Manage Users
        </Link>
        <Link
          href="/admin/roles"
          className="rounded-lg border px-4 py-2 text-sm hover:bg-accent transition flex items-center gap-2"
        >
          <ShieldCheck className="w-4 h-4" /> Role Policies
        </Link>
        <Link
          href="/admin/reports"
          className="rounded-lg border px-4 py-2 text-sm hover:bg-accent transition flex items-center gap-2"
        >
          <Activity className="w-4 h-4" /> Full Reports
        </Link>
      </div>
    </div>
  );
}
