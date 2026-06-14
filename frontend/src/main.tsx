import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router";
import { Toaster } from "sonner";
import App from "./App";
import { AuthProvider } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { ThemeProvider } from "@/theme/ThemeProvider";
import { WaveTransitionProvider } from "@/components/effects/transition-provider";
import { LoginPage } from "@/pages/LoginPage";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { SetupWizard } from "@/pages/SetupWizard";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";
import { ConnectingPage } from "@/pages/ConnectingPage";
import "./styles/globals.css";

/** Toaster that follows the app theme by mirroring the `.dark` class on <html>
 * (the single source of truth applyTheme toggles for light/dark/system). */
function ThemedToaster() {
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setIsDark(el.classList.contains("dark")));
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return <Toaster theme={isDark ? "dark" : "light"} />;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider>
        <AuthProvider>
          <WaveTransitionProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route path="/setup" element={<SetupWizard />} />
            <Route path="/accept-invite/:token" element={<AcceptInvitePage />} />
            <Route path="/connecting" element={<ConnectingPage />} />
            <Route path="/*" element={<ProtectedRoute><App /></ProtectedRoute>} />
          </Routes>
          </WaveTransitionProvider>
        </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
      <ThemedToaster />
    </QueryClientProvider>
  </StrictMode>
);
