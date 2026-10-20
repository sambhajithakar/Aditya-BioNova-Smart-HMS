"use client";

/**
 * Member administration (M7 contract): list members, create an account,
 * invite by e-mail, change role, suspend / reactivate, revoke a member's
 * sessions, and manage pending invitations. Reading needs member.read;
 * every change needs member.manage (buttons are hidden otherwise). The
 * owner cannot be modified and you cannot suspend yourself (enforced
 * server-side; mirrored here).
 *
 * In development the mock communications outbox (/dev/outbox) is shown so
 * invitation / reset links can be followed without real e-mail.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  ApiError,
  Branch,
  Invitation,
  Member,
  OutboxMessage,
  ROLE_KEYS,
  api,
} from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan, useMe } from "@/lib/me";
import { useInFlight } from "@/lib/idempotency";
import { PASSWORD_MAX, PASSWORD_MIN } from "@/lib/password";

function msg(err: unknown, fallback: string): string {
  return err instanceof ApiError && typeof err.detail === "string" ? err.detail : fallback;
}

const EMPTY_CREATE = { email: "", full_name: "", password: "", role_key: "", branch_id: "" };
const EMPTY_INVITE = { email: "", role_key: "", branch_id: "" };

function MembersBody() {
  const { t } = useLang();
  const me = useMe();
  const can = useCan();
  const manage = can("member.manage");
  const { busy, run } = useInFlight();
  const [members, setMembers] = useState<Member[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [outbox, setOutbox] = useState<OutboxMessage[] | null>(null);
  const [create, setCreate] = useState(EMPTY_CREATE);
  const [invite, setInvite] = useState(EMPTY_INVITE);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [ms, bs] = await Promise.all([
        api.get<Member[]>("/members"),
        api.get<Branch[]>("/branches").catch(() => [] as Branch[]),
      ]);
      setMembers(ms);
      setBranches(bs.filter((b) => b.status === "active"));
      if (manage) {
        setInvites(await api.get<Invitation[]>("/members/invitations").catch(() => []));
        // Dev-only endpoint: a 404 in other environments simply hides the panel.
        setOutbox(await api.get<OutboxMessage[]>("/dev/outbox?limit=20").catch(() => null));
      }
    } catch (err) {
      setError(msg(err, t("loadFailed")));
    }
  }, [manage, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = (fn: () => Promise<void>) =>
    run(async () => {
      setError(null);
      setNotice(null);
      try {
        await fn();
        await load();
      } catch (err) {
        setError(msg(err, t("actionFailed")));
      }
    });

  const branchName = (id: string | null) =>
    id ? branches.find((b) => b.id === id)?.name ?? id.slice(0, 8) : "—";

  const onCreate = (e: FormEvent) => {
    e.preventDefault();
    if (create.password.length < PASSWORD_MIN || create.password.length > PASSWORD_MAX) {
      setError(t("passwordPolicy"));
      return;
    }
    return act(async () => {
      await api.post<Member>("/members", {
        email: create.email,
        full_name: create.full_name,
        password: create.password,
        role_key: create.role_key,
        ...(create.branch_id ? { branch_id: create.branch_id } : {}),
      });
      setCreate(EMPTY_CREATE);
      setNotice(t("memberCreated"));
    });
  };

  const onInvite = (e: FormEvent) => {
    e.preventDefault();
    return act(async () => {
      await api.post<Invitation>("/members/invitations", {
        email: invite.email,
        role_key: invite.role_key,
        ...(invite.branch_id ? { branch_id: invite.branch_id } : {}),
      });
      setInvite(EMPTY_INVITE);
      setNotice(t("invitationSent"));
    });
  };

  const patch = (m: Member, body: Record<string, unknown>) =>
    act(async () => {
      await api.patch<Member>(`/members/${m.membership_id}`, body);
      setNotice(t("saved"));
    });

  const revokeSessions = (m: Member) =>
    act(async () => {
      const r = await api.post<{ revoked: number }>(`/members/${m.membership_id}/sessions/revoke`, {});
      setNotice(`${t("sessionsRevoked")}: ${r.revoked}`);
    });

  const revokeInvite = (i: Invitation) =>
    act(async () => {
      await api.post<Invitation>(`/members/invitations/${i.id}/revoke`, {});
    });

  const roleOptions = (
    <>
      <option value="">—</option>
      {ROLE_KEYS.map((r) => (
        <option key={r} value={r}>
          {t(`role_${r}`)}
        </option>
      ))}
    </>
  );
  const branchOptions = (
    <>
      <option value="">{t("allBranches")}</option>
      {branches.map((b) => (
        <option key={b.id} value={b.id}>
          {b.name}
        </option>
      ))}
    </>
  );

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("members")}</h1>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" aria-live="polite">
          {notice}
        </p>
      )}

      <section className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("fullName")}</th>
                <th scope="col">{t("email")}</th>
                <th scope="col">{t("role")}</th>
                <th scope="col">{t("branch")}</th>
                <th scope="col">{t("status")}</th>
                {manage && <th scope="col">{t("actions")}</th>}
              </tr>
            </thead>
            <tbody>
              {members.map((m) => {
                const isOwner = m.role_key === "owner";
                const isSelf = m.user_id === me?.user.id;
                const locked = isOwner || isSelf;
                return (
                  <tr key={m.membership_id}>
                    <td>{m.full_name}</td>
                    <td>{m.email}</td>
                    <td>
                      {manage && !locked ? (
                        <select
                          aria-label={`${t("role")} — ${m.full_name}`}
                          value={m.role_key}
                          disabled={busy}
                          onChange={(e) => void patch(m, { role_key: e.target.value })}
                        >
                          {ROLE_KEYS.map((r) => (
                            <option key={r} value={r}>
                              {t(`role_${r}`)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        t(`role_${m.role_key}`)
                      )}
                    </td>
                    <td>{branchName(m.branch_id)}</td>
                    <td>
                      <span className="tag">{t(m.status)}</span>
                    </td>
                    {manage && (
                      <td>
                        {!locked && m.status === "active" && (
                          <button
                            type="button"
                            className="danger"
                            disabled={busy}
                            onClick={() => void patch(m, { status: "suspended" })}
                          >
                            {t("suspend")}
                          </button>
                        )}
                        {!locked && m.status === "suspended" && (
                          <button
                            type="button"
                            className="secondary"
                            disabled={busy}
                            onClick={() => void patch(m, { status: "active" })}
                          >
                            {t("reactivate")}
                          </button>
                        )}
                        {!isOwner && (
                          <button
                            type="button"
                            className="secondary"
                            disabled={busy}
                            onClick={() => void revokeSessions(m)}
                          >
                            {t("revokeSessions")}
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {manage && (
        <div className="grid two" style={{ marginTop: "1.25rem" }}>
          <section className="card">
            <h2 style={{ marginTop: 0 }}>{t("inviteMember")}</h2>
            <form className="stack" onSubmit={onInvite}>
              <label className="field">
                {t("email")}
                <input
                  type="email"
                  value={invite.email}
                  onChange={(e) => setInvite({ ...invite, email: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                {t("role")}
                <select
                  value={invite.role_key}
                  onChange={(e) => setInvite({ ...invite, role_key: e.target.value })}
                  required
                >
                  {roleOptions}
                </select>
              </label>
              <label className="field">
                {t("branch")}
                <select
                  value={invite.branch_id}
                  onChange={(e) => setInvite({ ...invite, branch_id: e.target.value })}
                >
                  {branchOptions}
                </select>
              </label>
              <button type="submit" className="primary" disabled={busy}>
                {t("sendInvitation")}
              </button>
            </form>
          </section>

          <section className="card">
            <h2 style={{ marginTop: 0 }}>{t("createMember")}</h2>
            <form className="stack" onSubmit={onCreate}>
              <label className="field">
                {t("fullName")}
                <input
                  type="text"
                  value={create.full_name}
                  onChange={(e) => setCreate({ ...create, full_name: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                {t("email")}
                <input
                  type="email"
                  value={create.email}
                  onChange={(e) => setCreate({ ...create, email: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                {t("initialPassword")}
                <input
                  type="password"
                  autoComplete="new-password"
                  minLength={PASSWORD_MIN}
                  maxLength={PASSWORD_MAX}
                  value={create.password}
                  onChange={(e) => setCreate({ ...create, password: e.target.value })}
                  required
                />
              </label>
              <label className="field">
                {t("role")}
                <select
                  value={create.role_key}
                  onChange={(e) => setCreate({ ...create, role_key: e.target.value })}
                  required
                >
                  {roleOptions}
                </select>
              </label>
              <label className="field">
                {t("branch")}
                <select
                  value={create.branch_id}
                  onChange={(e) => setCreate({ ...create, branch_id: e.target.value })}
                >
                  {branchOptions}
                </select>
              </label>
              <button type="submit" className="primary" disabled={busy}>
                {t("createMember")}
              </button>
            </form>
          </section>
        </div>
      )}

      {manage && (
        <section className="card" style={{ marginTop: "1.25rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("invitations")}</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{t("email")}</th>
                  <th scope="col">{t("role")}</th>
                  <th scope="col">{t("branch")}</th>
                  <th scope="col">{t("status")}</th>
                  <th scope="col">{t("expiresAt")}</th>
                  <th scope="col">{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {invites.map((i) => (
                  <tr key={i.id}>
                    <td>{i.email}</td>
                    <td>{t(`role_${i.role_key}`)}</td>
                    <td>{branchName(i.branch_id)}</td>
                    <td>
                      <span className="tag">{t(i.status)}</span>
                    </td>
                    <td>{new Date(i.expires_at).toLocaleString()}</td>
                    <td>
                      {i.status === "pending" && (
                        <button
                          type="button"
                          className="danger"
                          disabled={busy}
                          onClick={() => void revokeInvite(i)}
                        >
                          {t("revoke")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {invites.length === 0 && (
                  <tr>
                    <td colSpan={6} className="muted">
                      —
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {manage && outbox && (
        <section className="card" style={{ marginTop: "1.25rem" }}>
          <h2 style={{ marginTop: 0 }}>{t("devOutbox")}</h2>
          <p className="muted">{t("devOutboxHint")}</p>
          <ul>
            {outbox.map((m) => (
              <li key={m.id}>
                <strong>{m.subject}</strong> → {m.to} ({m.channel},{" "}
                {new Date(m.created_at).toLocaleString()})
                <pre className="secret" style={{ whiteSpace: "pre-wrap" }}>
                  {m.body}
                </pre>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

export default function MembersPage() {
  return (
    <AppShell active="members">
      <MembersBody />
    </AppShell>
  );
}
