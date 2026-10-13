import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import english from '../public/locales/en/translation.json';
import hindi from '../public/locales/hi/translation.json';

let savedLanguage = 'en';
try {
  savedLanguage = localStorage.getItem('prism-language') === 'hi' ? 'hi' : 'en';
} catch { /* use English when browser storage is unavailable */ }

i18n
  .use(initReactI18next)
  .init({
    resources: { en: { translation: english }, hi: { translation: hindi } },
    lng: savedLanguage,
    fallbackLng: 'en',
    supportedLngs: ['en', 'hi'],
    load: 'languageOnly',
    interpolation: { escapeValue: false },
    initImmediate: false,
  });

export default i18n;
