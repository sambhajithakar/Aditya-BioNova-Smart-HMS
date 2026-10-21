"use client";

/**
 * Branches (M7.1): list, create, edit in place, activate / deactivate.
 * Reading needs branch.read, changes need branch.manage. Creating beyond the
 * edition's max_branches is refused by the API with "Plan limit reached: …",
 * which is shown as-is.
 */
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Messages, fmtDate, useAction } from "@/components/Saas";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { useCan } from "@/lib/me";
import { BranchOut, isValidGstin, normalizeGstin, serverMessage } from "@/lib/saas";

const EMPTY = { name: "", code: "", address: "", phone: "", gstin: "" };
type Draft = typeof EMPTY;

const orNull = (s: string) => (s.trim() === "" ? null : s.trim());

function BranchesBody() {
  const { t } = useLang();
  const can = useCan();
  const manage = can("branch.manage");
  const { busy, error, notice, setError, setNotice, act } = useAction();
  const [branches, setBranches] = useState<BranchOut[]>([]);
  const [create, setCreate] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [edit, setEdit] = useState<Draft>(EMPTY);

  const load = useCallback(async () => {
    try {
      setBranches(await api.get<BranchOut[]>("/branches"));
    } catch (err) {
      setError(serverMessage(err, t("loadFailed")));
    }
  }, [setError, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = (e: FormEvent) => {
    e.preventDefault();
    const gstin = normalizeGstin(create.gstin);
    if (!isValidGstin(gstin)) {
      setError(t("invalidGstin"));
      return;
    }
    void act(async () => {
      await api.post<BranchOut>("/branches", {
        name: create.name.trim(),
        code: create.code.trim(),
        address: orNull(create.address),
        phone: orNull(create.phone),
        gstin: orNull(gstin),
      });
      setCreate(EMPTY);
      setNotice(t("saved"));
      await load();
    });
  };

  const startEdit = (b: BranchOut) => {
    setEditing(b.id);
    setEdit({
      name: b.name,
      code: b.code,
      address: b.address ?? "",
      phone: b.phone ?? "",
      gstin: b.gstin ?? "",
    });
  };

  const onSaveEdit = (e: FormEvent) => {
    e.preventDefault();
    if (!editing) return;
    const gstin = normalizeGstin(edit.gstin);
    if (!isValidGstin(gstin)) {
      setError(t("invalidGstin"));
      return;
    }
    void act(async () => {
      await api.patch<BranchOut>(`/branches/${editing}`, {
        name: edit.name.trim(),
        address: orNull(edit.address),
        phone: orNull(edit.phone),
        gstin: orNull(gstin),
      });
      setEditing(null);
      setNotice(t("saved"));
      await load();
    });
  };

  const setStatus = (b: BranchOut, status: "active" | "inactive") =>
    void act(async () => {
      await api.patch<BranchOut>(`/branches/${b.id}`, { status });
      setNotice(t("saved"));
      await load();
    });

  const fields = (d: Draft, setD: (d: Draft) => void, isCreate: boolean, idp: string) => (
    <div className="grid two">
      <label className="field">
        {t("branchName")}
        <input
          type="text"
          id={`${idp}-name`}
          value={d.name}
          maxLength={200}
          onChange={(e) => setD({ ...d, name: e.target.value })}
          required
        />
      </label>
      {isCreate && (
        <label className="field">
          {t("branchCode")}
          <input
            type="text"
            id={`${idp}-code`}
            value={d.code}
            maxLength={20}
            onChange={(e) => setD({ ...d, code: e.target.value })}
            required
            aria-describedby={`${idp}-code-hint`}
          />
          <span className="muted" id={`${idp}-code-hint`} style={{ fontWeight: 400, fontSize: "0.85rem" }}>
            {t("branchCodeFixed")}
          </span>
        </label>
      )}
      <label className="field">
        {t("address")}
        <input
          type="text"
          value={d.address}
          maxLength={500}
          onChange={(e) => setD({ ...d, address: e.target.value })}
        />
      </label>
      <label className="field">
        {t("phone")}
        <input
          type="text"
          inputMode="tel"
          value={d.phone}
          maxLength={20}
          onChange={(e) => setD({ ...d, phone: e.target.value })}
        />
      </label>
      <label className="field">
        {t("gstin")}
        <input
          type="text"
          value={d.gstin}
          maxLength={15}
          autoCapitalize="characters"
          aria-invalid={!isValidGstin(normalizeGstin(d.gstin)) && d.gstin.length >= 15 ? true : undefined}
          onChange={(e) => setD({ ...d, gstin: e.target.value })}
        />
      </label>
    </div>
  );

  return (
    <main className="page">
      <h1 style={{ marginTop: 0 }}>{t("navBranches")}</h1>
      <Messages error={error} notice={notice} />

      <section className="card">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t("branchName")}</th>
                <th scope="col">{t("branchCode")}</th>
                <th scope="col">{t("address")}</th>
                <th scope="col">{t("phone")}</th>
                <th scope="col">{t("gstin")}</th>
                <th scope="col">{t("status")}</th>
                <th scope="col">{t("createdAt")}</th>
                {manage && <th scope="col">{t("actions")}</th>}
              </tr>
            </thead>
            <tbody>
              {branches.map((b) => (
                <tr key={b.id} data-testid={`branch-${b.code}`}>
                  <td>{b.name}</td>
                  <td>{b.code}</td>
                  <td>{b.address || "—"}</td>
                  <td>{b.phone || "—"}</td>
                  <td>{b.gstin || "—"}</td>
                  <td>
                    <span className="tag">{b.status === "active" ? t("active") : t("inactive")}</span>
                  </td>
                  <td>{fmtDate(b.created_at)}</td>
                  {manage && (
                    <td>
                      <button
                        type="button"
                        className="secondary"
                        disabled={busy}
                        onClick={() => startEdit(b)}
                        aria-label={`${t("edit")} — ${b.name}`}
                      >
                        {t("edit")}
                      </button>{" "}
                      {b.status === "active" ? (
                        <button
                          type="button"
                          className="danger"
                          disabled={busy}
                          onClick={() => setStatus(b, "inactive")}
                          aria-label={`${t("deactivate")} — ${b.name}`}
                        >
                          {t("deactivate")}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="secondary"
                          disabled={busy}
                          onClick={() => setStatus(b, "active")}
                          aria-label={`${t("activate")} — ${b.name}`}
                        >
                          {t("activate")}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
              {branches.length === 0 && (
                <tr>
                  <td colSpan={manage ? 8 : 7} className="muted">
                    {t("noBranches")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {manage && editing && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="edit-branch-h">
          <h2 id="edit-branch-h" style={{ marginTop: 0 }}>
            {t("edit")}: {edit.code}
          </h2>
          <form onSubmit={onSaveEdit}>
            {fields(edit, setEdit, false, "edit")}
            <div className="row" style={{ marginTop: "1rem" }}>
              <button type="submit" className="primary" disabled={busy}>
                {t("save")}
              </button>
              <button type="button" className="secondary" onClick={() => setEditing(null)}>
                {t("cancel")}
              </button>
            </div>
          </form>
        </section>
      )}

      {manage && (
        <section className="card" style={{ marginTop: "1.25rem" }} aria-labelledby="new-branch-h">
          <h2 id="new-branch-h" style={{ marginTop: 0 }}>
            {t("newBranch")}
          </h2>
          <form onSubmit={onCreate}>
            {fields(create, setCreate, true, "new")}
            <button type="submit" className="primary" disabled={busy} style={{ marginTop: "1rem" }}>
              {t("newBranch")}
            </button>
          </form>
        </section>
      )}
    </main>
  );
}

export default function BranchesPage() {
  return (
    <AppShell active="branches">
      <BranchesBody />
    </AppShell>
  );
}
