import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ChatStandalone } from "./ChatStandalone";
import "./theme/tokens.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ChatStandalone />
  </StrictMode>,
);
