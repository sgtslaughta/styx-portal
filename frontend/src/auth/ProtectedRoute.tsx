import { type ReactNode } from "react";
import { Navigate } from "react-router";
import { useAuth } from "@/hooks/use-auth";

export function ProtectedRoute({ children, adminOnly = false }: { children: ReactNode; adminOnly?: boolean }) {
  const { user, loading, setupRequired } = useAuth();
  if (loading) return <div className="grid h-screen place-items-center">Loading…</div>;
  if (setupRequired) return <Navigate to="/setup" replace />;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}
