"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useLang } from "@/lib/lang";
import { SlotsOut } from "@/lib/setup";

/** Free slots from the branch's working hours (GET /appointments/slots).
 * Suggestions only — booking still accepts any time the desk chooses. */
export function SlotSuggestions({
  branchId,
  date,
  onPick,
}: {
  branchId: string;
  date: string;
  onPick: (hhmm: string, minutes: number) => void;
}) {
  const { t } = useLang();
  const [data, setData] = useState<SlotsOut | null>(null);
  useEffect(() => {
    setData(null);
    if (!branchId || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
    let cancelled = false;
    api
      .get<SlotsOut>(`/appointments/slots?branch_id=${branchId}&date=${date}`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [branchId, date]);
  if (!data) return null;
  if (!data.configured) {
    return <p className="muted" style={{ fontSize: "0.85rem", flexBasis: "100%" }}>{t("slotsNotConfigured")}</p>;
  }
  const free = data.slots.filter((s) => s.available);
  return (
    <div style={{ flexBasis: "100%" }} data-testid="slot-suggestions">
      <span className="muted" style={{ fontSize: "0.85rem" }}>
        {free.length ? t("slotsFree") : t("slotsNone")}
      </span>{" "}
      {free.slice(0, 24).map((s) => {
        const local = new Date(s.starts_at).toLocaleTimeString("en-GB", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "Asia/Kolkata",
        });
        return (
          <button key={s.starts_at} type="button" className="chip" onClick={() => onPick(local, data.slot_minutes)}>
            {local}
          </button>
        );
      })}
    </div>
  );
}
