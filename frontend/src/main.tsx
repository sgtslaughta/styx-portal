import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router";
import { ThemedToaster } from "@/components/themed-toaster";
import { MotionConfig } from "framer-motion";
import App from "./App";
import { applyReducedMotion } from "@/lib/motion";
import { AuthProvider } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { ThemeProvider } from "@/theme/ThemeProvider";
import { WaveTransitionProvider } from "@/components/effects/transition-provider";
import { OpenPrefProvider } from "@/components/open-prompt";
import { LoginPage } from "@/pages/LoginPage";
import { ChangePasswordPage } from "@/pages/ChangePasswordPage";
import { SetupWizard } from "@/pages/SetupWizard";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";
import { ConnectingPage } from "@/pages/ConnectingPage";
import "@fontsource-variable/commissioner/flar.css";
import "./styles/globals.css";

applyReducedMotion();

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
      <MotionConfig reducedMotion="user">
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
            <Route path="/*" element={<ProtectedRoute><OpenPrefProvider><App /></OpenPrefProvider></ProtectedRoute>} />
          </Routes>
          </WaveTransitionProvider>
        </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
      </MotionConfig>
      <ThemedToaster />
    </QueryClientProvider>
  </StrictMode>
);
