import { createContext, useContext, useEffect } from "react";
import { useTranslation } from "react-i18next";
import english from "../../public/locales/en/translation.json";
import hindi from "../../public/locales/hi/translation.json";

const LanguageContext = createContext();
const sourceText = new WeakMap();
const sourceToHindi = english.ui;
const hindiToSource = new Map(Object.entries(hindi.ui).map(([source, translated]) => [translated, source]));

function sourceFor(node) {
  const text = node.nodeValue || "";
  const trimmed = text.replace(/\s+/g, " ").trim();
  const cached = sourceText.get(node);
  if (cached && cached.rendered === trimmed) return cached.source;
  const source = Object.hasOwn(sourceToHindi, trimmed) ? trimmed : hindiToSource.get(trimmed);
  if (source) sourceText.set(node, { source, rendered: trimmed });
  return source;
}

function translateTextNode(node, language) {
  const parent = node.parentElement;
  if (!parent || parent.closest("script,style,textarea,input,select,option,pre,code,[contenteditable='true']")) return;
  const source = sourceFor(node);
  if (!source) return;
  const original = node.nodeValue || "";
  const leading = original.match(/^\s*/)?.[0] || "";
  const trailing = original.match(/\s*$/)?.[0] || "";
  const translated = language === "hi" ? (sourceToHindi[source] || source) : source;
  const next = `${leading}${translated}${trailing}`;
  sourceText.set(node, { source, rendered: translated });
  if (node.nodeValue !== next) node.nodeValue = next;
}

function translateElement(element, language) {
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) translateTextNode(node, language);
  const attributes = ["placeholder", "title", "aria-label", "aria-description", "alt"];
  for (const item of [element, ...element.querySelectorAll("*")]) {
    for (const attribute of attributes) {
      const value = item.getAttribute?.(attribute);
      if (!value) continue;
      const source = Object.hasOwn(sourceToHindi, value) ? value : hindiToSource.get(value);
      const translated = source && (language === "hi" ? (sourceToHindi[source] || source) : source);
      if (translated && translated !== value) item.setAttribute(attribute, translated);
    }
  }
}

export const LanguageProvider = ({ children }) => {
  const { i18n } = useTranslation();
  const language = (i18n.resolvedLanguage || i18n.language || "en").split("-")[0];

  useEffect(() => {
    document.documentElement.lang = language;
    try { localStorage.setItem("prism-language", language); } catch { /* storage may be disabled */ }
    translateElement(document.body, language);
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        if (record.type === "characterData") translateTextNode(record.target, language);
        if (record.type === "childList") record.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) translateTextNode(node, language);
          else if (node.nodeType === Node.ELEMENT_NODE) translateElement(node, language);
        });
        if (record.type === "attributes") translateElement(record.target, language);
      }
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "aria-description", "alt"] });
    return () => observer.disconnect();
  }, [language]);

  const toggleLanguage = () => {
    const next = language === "en" ? "hi" : "en";
    i18n.changeLanguage(next).then(() => {
      try { localStorage.setItem("prism-language", next); } catch { /* storage may be disabled */ }
    });
  };

  return (
    <LanguageContext.Provider
      value={{
        language,
        toggleLanguage,
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export const useLanguage = () => useContext(LanguageContext);
