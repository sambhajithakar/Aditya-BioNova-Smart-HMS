"use client";

/**
 * Language context (fixes D19): one source of truth for the UI language so
 * switching in the header re-renders every page body, and <html lang> is
 * kept in sync for screen readers / hyphenation.
 */
import { ReactNode, createContext, useCallback, useContext, useEffect, useState } from "react";
import { Lang, getLang, setLang as persistLang, t as translate } from "./i18n";

type LangCtx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
};

const Ctx = createContext<LangCtx>({
  lang: "en",
  setLang: () => undefined,
  t: (k) => translate(k, "en"),
});

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setState] = useState<Lang>("en");

  useEffect(() => {
    setState(getLang());
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    persistLang(l);
    setState(l);
  }, []);

  const t = useCallback((k: string) => translate(k, lang), [lang]);

  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export function useLang(): LangCtx {
  return useContext(Ctx);
}
