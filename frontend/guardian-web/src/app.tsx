import React from "react";
import AppRouter from "./routes/app-router";
import { LanguageProvider } from "./i18n/language-context";

const App = () => {
  return (
    <LanguageProvider>
      <AppRouter />
    </LanguageProvider>
  );
};

export default App;