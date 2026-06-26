import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import './i18n';
import { LanguageProvider } from "./components/LanguageContext";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <LanguageProvider>
      <App />
    </LanguageProvider>
  </React.StrictMode>
);