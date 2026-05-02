"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Shield,
  Plus,
  Trash2,
  Save,
  ChevronDown,
  ChevronUp,
  Loader2,
  AlertTriangle,
  Clock,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import { adminApi, RoleRecord, RolePolicyRecord } from "@/lib/admin-api";
import TagInput from "@/components/admin/TagInput";

interface PolicyDraft extends Partial<RolePolicyRecord> {}

// ---------------------------------------------------------------------------
// Toggle switch
// ---------------------------------------------------------------------------
function Toggle({
  value,
  onChange,
  disabled,
}: {
  value: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!value)}
      disabled={disabled}
      className="focus:outline-none disabled:opacity-50"
    >
      {value ? (
        <ToggleRight size={28} className="text-primary" />
      ) : (
        <ToggleLeft size={28} className="text-muted-foreground/40" />
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Field row
// ---------------------------------------------------------------------------
function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        {label}
      </label>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PolicyEditor
// ---------------------------------------------------------------------------
function PolicyEditor({
  policy,
  onSave,
  saving,
}: {
  policy: RolePolicyRecord;
  onSave: (draft: PolicyDraft) => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<PolicyDraft>({ ...policy });
  const [timeEnabled, setTimeEnabled] = useState(
    !!(policy.time_restriction_start || policy.time_restriction_end)
  );

  function patch<K extends keyof PolicyDraft>(key: K, value: PolicyDraft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload: PolicyDraft = { ...draft };
    if (!timeEnabled) {
      payload.time_restriction_start = null;
      payload.time_restriction_end = null;
    }
    onSave(payload);
  }

  const inputCls =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";
  const selectCls =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <form onSubmit={handleSubmit} className="space-y-5 pt-4">
      {/* ── Core limits ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <FieldRow label="Security level">
          <select
            value={draft.security_level ?? "medium"}
            onChange={(e) => patch("security_level", e.target.value)}
            className={selectCls}
          >
            {["low", "medium", "high"].map((l) => (
              <option key={l} value={l}>
                {l.charAt(0).toUpperCase() + l.slice(1)}
              </option>
            ))}
          </select>
        </FieldRow>

        <FieldRow label="Max prompt length (chars)">
          <input
            type="number"
            min={100}
            max={32000}
            value={draft.max_prompt_length ?? 2000}
            onChange={(e) => patch("max_prompt_length", Number(e.target.value))}
            className={inputCls}
          />
        </FieldRow>

        <FieldRow label="Max requests / day">
          <input
            type="number"
            min={1}
            max={10000}
            value={draft.max_requests_per_day ?? 100}
            onChange={(e) => patch("max_requests_per_day", Number(e.target.value))}
            className={inputCls}
          />
        </FieldRow>
      </div>

      {/* ── Session controls ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FieldRow label="Max conversation turns">
          <input
            type="number"
            min={1}
            max={500}
            value={draft.max_conversation_turns ?? 50}
            onChange={(e) => patch("max_conversation_turns", Number(e.target.value))}
            className={inputCls}
          />
        </FieldRow>

        <FieldRow label="Session timeout (minutes)">
          <input
            type="number"
            min={1}
            max={1440}
            value={draft.session_timeout_minutes ?? 60}
            onChange={(e) => patch("session_timeout_minutes", Number(e.target.value))}
            className={inputCls}
          />
        </FieldRow>
      </div>

      {/* ── Feature toggles ── */}
      <div className="rounded-lg border bg-muted/30 divide-y">
        {(
          [
            [
              "enforce_topic_restrictions",
              "Enforce topic restrictions",
              "Block prompts that fall outside the allowed topics list",
            ],
            [
              "response_filter_enabled",
              "Response filtering",
              "Scan LLM output for sensitive content before delivery",
            ],
            [
              "allow_file_uploads",
              "Allow file uploads",
              "Users with this role can attach files to their prompts",
            ],
          ] as [keyof PolicyDraft, string, string][]
        ).map(([key, label, hint]) => (
          <div
            key={key}
            className="flex items-center justify-between px-4 py-3 gap-4"
          >
            <div>
              <p className="text-sm font-medium text-foreground">{label}</p>
              <p className="text-xs text-muted-foreground">{hint}</p>
            </div>
            <Toggle
              value={!!draft[key]}
              onChange={(v) => patch(key, v as never)}
            />
          </div>
        ))}
      </div>

      {/* ── Time restrictions ── */}
      <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Clock size={16} />
            <span className="text-sm font-medium text-foreground">
              Time-of-day restrictions (UTC)
            </span>
          </div>
          <Toggle value={timeEnabled} onChange={setTimeEnabled} />
        </div>

        {timeEnabled && (
          <div className="grid grid-cols-2 gap-4 pt-1">
            <FieldRow label="Start (HH:MM)">
              <input
                type="time"
                value={draft.time_restriction_start ?? ""}
                onChange={(e) => patch("time_restriction_start", e.target.value || null)}
                className={inputCls}
              />
            </FieldRow>
            <FieldRow label="End (HH:MM)">
              <input
                type="time"
                value={draft.time_restriction_end ?? ""}
                onChange={(e) => patch("time_restriction_end", e.target.value || null)}
                className={inputCls}
              />
            </FieldRow>
          </div>
        )}
      </div>

      {/* ── Topic control ── */}
      <div className="space-y-4">
        <FieldRow label="Allowed topics">
          <TagInput
            tags={draft.allowed_topics ?? []}
            onChange={(t) => patch("allowed_topics", t)}
            placeholder="e.g. software, devops — press Enter or comma to add"
          />
          <p className="text-xs text-muted-foreground mt-1">
            Used with "Enforce topic restrictions" to classify incoming prompts.
          </p>
        </FieldRow>

        <FieldRow label="Blocked topics / keywords">
          <TagInput
            tags={draft.blocked_topics ?? []}
            onChange={(t) => patch("blocked_topics", t)}
            placeholder="e.g. salary, legal — always rejected regardless of allowed list"
          />
        </FieldRow>
      </div>

      {/* ── System prompt ── */}
      <FieldRow label="System prompt (injected before every conversation)">
        <textarea
          rows={4}
          value={draft.system_prompt ?? ""}
          onChange={(e) => patch("system_prompt", e.target.value || null)}
          placeholder="You are a helpful assistant for…"
          className={`${inputCls} resize-y`}
        />
      </FieldRow>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-medium disabled:opacity-60 transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Save policy
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// RoleCard
// ---------------------------------------------------------------------------
function RoleCard({
  role,
  onPolicySave,
  onDelete,
}: {
  role: RoleRecord;
  onPolicySave: (roleId: number, draft: PolicyDraft) => Promise<void>;
  onDelete: (role: RoleRecord) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave(draft: PolicyDraft) {
    setSaving(true);
    setError(null);
    try {
      await onPolicySave(role.id, draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border bg-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
              role.is_admin ? "bg-purple-500/10" : "bg-primary/10"
            }`}
          >
            <Shield
              size={14}
              className={role.is_admin ? "text-purple-600" : "text-primary"}
            />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-foreground truncate">
                {role.name}
              </span>
              {role.is_admin && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-600 border border-purple-300">
                  admin
                </span>
              )}
            </div>
            {role.description && (
              <p className="text-xs text-muted-foreground truncate">
                {role.description}
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {!role.is_admin && (
            <button
              onClick={() => onDelete(role)}
              className="p-1.5 rounded text-muted-foreground hover:text-red-600 hover:bg-red-500/10 transition-colors"
              title="Delete role"
            >
              <Trash2 size={14} />
            </button>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            Edit policy
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Quick stats strip */}
      {role.policy && !expanded && (
        <div className="px-5 pb-3 flex flex-wrap gap-4">
          {[
            ["Security", role.policy.security_level],
            ["Max length", `${role.policy.max_prompt_length} chars`],
            ["Req/day", String(role.policy.max_requests_per_day)],
            ["Turns", String(role.policy.max_conversation_turns)],
          ].map(([k, v]) => (
            <div key={k} className="text-xs text-muted-foreground">
              <span className="font-medium text-foreground">{k}: </span>
              {v}
            </div>
          ))}
        </div>
      )}

      {/* Expanded editor */}
      {expanded && (
        <div className="border-t px-5 pb-5">
          {error && (
            <div className="mt-4 flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-200 text-red-600 text-sm">
              <AlertTriangle size={14} />
              {error}
            </div>
          )}
          {role.policy ? (
            <PolicyEditor policy={role.policy} onSave={handleSave} saving={saving} />
          ) : (
            <div className="pt-4 text-sm text-muted-foreground">
              No policy yet.{" "}
              <button
                onClick={() => onPolicySave(role.id, {})}
                className="text-primary hover:underline"
              >
                Create default policy
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AddRoleForm
// ---------------------------------------------------------------------------
function AddRoleForm({
  onAdd,
  onCancel,
}: {
  onAdd: (name: string, description: string, isAdmin: boolean) => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inputCls =
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await onAdd(
        name.trim().toLowerCase().replace(/\s+/g, "_"),
        description,
        isAdmin
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create role");
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-primary/20 bg-primary/5 p-5 space-y-4"
    >
      <h3 className="text-sm font-semibold text-foreground">Create new role</h3>

      {error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-200 text-red-600 text-sm">
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FieldRow label="Role name (lowercase, underscores)">
          <input
            required
            pattern="^[a-z0-9_-]+$"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. data_analyst"
            className={inputCls}
          />
        </FieldRow>

        <FieldRow label="Description (optional)">
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. Data science team"
            className={inputCls}
          />
        </FieldRow>
      </div>

      <div className="flex items-center gap-3">
        <Toggle value={isAdmin} onChange={setIsAdmin} />
        <span className="text-sm text-muted-foreground">Grant admin access</span>
      </div>

      <div className="flex gap-3 justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg border text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving || !name.trim()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-medium disabled:opacity-60 transition-colors"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          Create role
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------
function DeleteConfirmDialog({
  role,
  onConfirm,
  onCancel,
  deleting,
  error,
}: {
  role: RoleRecord;
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
  error: string | null;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl border bg-card p-6 space-y-4 shadow-2xl">
        <div className="flex items-center gap-3 text-red-600">
          <AlertTriangle size={20} />
          <h2 className="font-semibold text-lg">Delete role "{role.name}"?</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          This will permanently delete the role and its policy. You cannot
          delete a role that has active users assigned — reassign them first.
        </p>
        {error && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-200 text-red-600 text-sm">
            <AlertTriangle size={14} />
            {error}
          </div>
        )}
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg border text-sm text-muted-foreground hover:bg-accent transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium disabled:opacity-60 transition-colors"
          >
            {deleting && <Loader2 size={14} className="animate-spin" />}
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function RolesPage() {
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RoleRecord | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchRoles = useCallback(async () => {
    try {
      const data = await adminApi.roles.list();
      setRoles(data);
    } catch (e) {
      setPageError(e instanceof Error ? e.message : "Failed to load roles");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRoles();
  }, [fetchRoles]);

  async function handlePolicySave(roleId: number, draft: PolicyDraft) {
    if (Object.keys(draft).length === 0) {
      await adminApi.roles.createPolicy(roleId);
    } else {
      await adminApi.roles.updatePolicy(roleId, draft as Partial<RolePolicyRecord>);
    }
    await fetchRoles();
  }

  async function handleAddRole(name: string, description: string, isAdmin: boolean) {
    await adminApi.roles.create({ name, description, is_admin: isAdmin });
    setShowAddForm(false);
    await fetchRoles();
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      const res = await adminApi.roles.delete(deleteTarget.id);
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: "Delete failed" }));
        throw new Error(body.detail);
      }
      setDeleteTarget(null);
      await fetchRoles();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Roles &amp; Policies</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Create, configure, and delete roles. Each role has a policy that
            controls what users can do.
          </p>
        </div>
        <button
          onClick={() => setShowAddForm((v) => !v)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-medium transition-colors"
        >
          <Plus size={14} />
          Add role
        </button>
      </div>

      {/* Add role form */}
      {showAddForm && (
        <AddRoleForm
          onAdd={handleAddRole}
          onCancel={() => setShowAddForm(false)}
        />
      )}

      {/* Error */}
      {pageError && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-500/10 border border-red-200 text-red-600 text-sm">
          <AlertTriangle size={14} />
          {pageError}
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 size={24} className="animate-spin mr-2" />
          Loading roles…
        </div>
      ) : (
        <div className="space-y-4">
          {roles.map((role) => (
            <RoleCard
              key={role.id}
              role={role}
              onPolicySave={handlePolicySave}
              onDelete={setDeleteTarget}
            />
          ))}
          {roles.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              No roles found. Create one above.
            </div>
          )}
        </div>
      )}

      {/* Delete dialog */}
      {deleteTarget && (
        <DeleteConfirmDialog
          role={deleteTarget}
          onConfirm={handleDeleteConfirm}
          onCancel={() => {
            setDeleteTarget(null);
            setDeleteError(null);
          }}
          deleting={deleting}
          error={deleteError}
        />
      )}
    </div>
  );
}
