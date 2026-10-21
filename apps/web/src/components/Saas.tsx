"use client";

/**
 * Small shared pieces for the M7.1 tenant-admin and platform pages:
 * error / notice messages, the usage meter, and a guarded action runner that
 * surfaces the server's own message (402 read-only, 403 feature / plan
 * limit) instead of a generic failure.
 */
import { useCallback, useState } from "react";
import { useInFlight } from "@/lib/idempotency";
import { useLang } from "@/lib/lang";
import { SupportTicketDetail, UsageEntry, serverMessage, usageMeter } from "@/lib/saas";

export function Messages({ error, notice }: { error: string | null; notice: string | null }) {
  return (
    <>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="notice" role="status" aria-live="polite">
          {notice}
        </p>
      )}
    </>
  );
}

/**
 * `act(fn)`: clears messages, runs fn once at a time (double-submit guard),
 * and shows the server's message on failure. Resolves to true on success.
 */
export function useAction() {
  const { t } = useLang();
  const { busy, run } = useInFlight();
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const act = useCallback(
    async (fn: () => Promise<void>): Promise<boolean> =>
      (await run(async () => {
        setError(null);
        setNotice(null);
        try {
          await fn();
          return true;
        } catch (err) {
          setError(serverMessage(err, t("actionFailed")));
          return false;
        }
      })) ?? false,
    [run, t],
  );
  return { busy, error, notice, setError, setNotice, act };
}

export function UsageMeter({ label, entry }: { label: string; entry: UsageEntry }) {
  const { t } = useLang();
  const m = usageMeter(entry);
  const figure = m.unlimited
    ? `${m.used} · ${t("unlimited")}`
    : `${m.used} ${t("usageOf")} ${m.limit}`;
  return (
    <div className={`meter ${m.state}`}>
      <span style={{ fontWeight: 600 }}>{label}</span>
      {m.unlimited ? null : (
        <div
          className="bar"
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={m.limit ?? 0}
          aria-valuenow={Math.min(m.used, m.limit ?? 0)}
          aria-valuetext={figure}
        >
          <div className="fill" style={{ width: `${m.percent}%` }} />
        </div>
      )}
      <span className="figure">{figure}</span>
    </div>
  );
}

export function TicketThread({ ticket }: { ticket: SupportTicketDetail }) {
  const { t } = useLang();
  return (
    <ol className="thread" aria-label={t("conversation")} data-testid="ticket-thread">
      {ticket.messages.map((m) => (
        <li
          key={m.id}
          className={m.internal ? "internal" : m.author_side === "vendor" ? "vendor" : undefined}
        >
          <div className="meta">
            <strong>{m.author_name ?? t(`side_${m.author_side}`)}</strong> ·{" "}
            {t(`side_${m.author_side}`)} · {fmtDateTime(m.created_at)}
            {m.internal && (
              <>
                {" "}
                <span className="tag">{t("internalTag")}</span>
              </>
            )}
          </div>
          {m.body}
        </li>
      ))}
    </ol>
  );
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}
