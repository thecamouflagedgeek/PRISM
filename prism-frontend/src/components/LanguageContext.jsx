import { createContext, useContext } from "react";
import { useTranslation } from "react-i18next";

const LanguageContext = createContext();

export const LanguageProvider = ({ children }) => {
  const { i18n } = useTranslation();

  const toggleLanguage = () => {
    const next = i18n.language === "en" ? "hi" : "en";
    i18n.changeLanguage(next);
  };

  return (
    <LanguageContext.Provider
      value={{
        language: i18n.language,
        toggleLanguage,
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => useContext(LanguageContext);