import React from "react";
import ReactDOM from "react-dom/client";
import App from "./app";
import "./styles/index.css";
import { printCredits } from "@shared/utils/credits";

printCredits();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);