"use client";

/**
 * "?" help dialog. Loaded on demand with next/dynamic (it is rarely opened),
 * built on the native modal <dialog>: focus moves into it, Esc closes it and
 * focus returns to where it was.
 */
import { useEffect, useRef } from "react";
import { useLang } from "@/lib/lang";
import { NAV, navLabel } from "@/lib/nav";
import { SHORTCUT_HELP } from "@/lib/shortcuts";

export default function ShortcutsDialog({
  onClose,
  visibleNavKeys,
}: {
  onClose: () => void;
  visibleNavKeys: string[];
}) {
  const { t } = useLang();
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    const opener = document.activeElement as HTMLElement | null;
    if (d && !d.open) d.showModal();
    return () => {
      opener?.focus?.();
    };
  }, []);

  const rows = SHORTCUT_HELP.filter((r) => !r.nav || visibleNavKeys.includes(r.nav));

  return (
    <dialog
      ref={ref}
      className="sheet-dialog shortcuts-dialog"
      aria-labelledby="shortcuts-title"
      onClose={onClose}
      onCancel={onClose}
      data-testid="shortcuts-dialog"
    >
      <div className="sheet-head">
        <h2 id="shortcuts-title">{t("devShortcutsTitle")}</h2>
        <button type="button" className="secondary" onClick={() => ref.current?.close()} autoFocus>
          {t("devClose")}
        </button>
      </div>
      <p className="muted">{t("devShortcutsHint")}</p>
      <table className="shortcuts-table">
        <tbody>
          {rows.map((r) => {
            const item = r.nav ? NAV.find((n) => n.key === r.nav) : undefined;
            return (
              <tr key={r.keys.join("+") + r.label + (r.nav ?? "")}>
                <td className="keys">
                  {r.keys.map((k, i) => (
                    <span key={k + i}>
                      {i > 0 && (
                        <span className="muted"> {r.keys[0] === "g" ? t("devScThen") : "+"} </span>
                      )}
                      <kbd>{k}</kbd>
                    </span>
                  ))}
                </td>
                <td>
                  {t(r.label)}
                  {item && <>: {t(navLabel(item))}</>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p>
        <a href="/print/test" target="_blank" rel="noopener noreferrer">
          {t("devPrinterTestLink")}
        </a>
      </p>
    </dialog>
  );
}
