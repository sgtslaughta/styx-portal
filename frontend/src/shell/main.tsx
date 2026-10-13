import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ShellApp } from "./shell-app";
import "@fontsource-variable/commissioner/flar.css";
import "@/styles/globals.css";

// CSP forbids inline scripts, so the theme class is applied here (mirrors index.html).
let t: string | null = null;
try { t = localStorage.getItem("theme"); } catch { /* storage blocked */ }
document.documentElement.classList.toggle(
  "dark",
  t === "dark" || (t !== "light" && matchMedia("(prefers-color-scheme:dark)").matches),
);

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ShellApp />
    </QueryClientProvider>
  </StrictMode>,
);
