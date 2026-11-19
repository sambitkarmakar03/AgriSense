import type { PropsWithChildren } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./useAuth";
import { LoadingState } from "../components/States";

export function ProtectedRoute({ children }: PropsWithChildren) {
  const { user, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) return <LoadingState label="Restoring your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

export function PublicOnlyRoute({ children }: PropsWithChildren) {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState label="Restoring your session" />;
  if (user) return <Navigate to="/" replace />;
  return children;
}
