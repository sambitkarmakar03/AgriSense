import { lazy, Suspense } from "react";
import type { ReactNode } from "react";
import { Route, Routes, Link } from "react-router-dom";
import { ProtectedRoute, PublicOnlyRoute } from "./auth/RouteGuards";
import { AppShell } from "./components/AppShell";
import { WakeServerBanner } from "./components/WakeServerBanner";
import { LoadingState } from "./components/States";

const LoginPage = lazy(() => import("./pages/AuthPages").then((module) => ({ default: module.LoginPage })));
const RegisterPage = lazy(() => import("./pages/AuthPages").then((module) => ({ default: module.RegisterPage })));
const AboutPage = lazy(() => import("./pages/AboutPage").then((module) => ({ default: module.AboutPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const FieldDetailPage = lazy(() => import("./pages/FieldDetailPage").then((module) => ({ default: module.FieldDetailPage })));
const FieldsPage = lazy(() => import("./pages/FieldsPage").then((module) => ({ default: module.FieldsPage })));
const IrrigationPage = lazy(() => import("./pages/IrrigationPage").then((module) => ({ default: module.IrrigationPage })));
const LimitationsPage = lazy(() => import("./pages/LimitationsPage").then((module) => ({ default: module.LimitationsPage })));

function LazyRoute({ children }: { children: ReactNode }) {
  return <Suspense fallback={<LoadingState label="Opening this page" />}>{children}</Suspense>;
}

function NotFoundPage() {
  return <div className="not-found"><p className="eyebrow">404 · OFF THE MAP</p><h1>We can’t find that field.</h1><p>The page may have moved, or the address may be incomplete.</p><Link className="button button-primary" to="/">Return to overview</Link></div>;
}

export default function App() {
  return <>
    <WakeServerBanner />
    <Routes>
      <Route path="/login" element={<PublicOnlyRoute><LazyRoute><LoginPage /></LazyRoute></PublicOnlyRoute>} />
      <Route path="/register" element={<PublicOnlyRoute><LazyRoute><RegisterPage /></LazyRoute></PublicOnlyRoute>} />
      <Route path="/limitations" element={<LazyRoute><LimitationsPage /></LazyRoute>} />
      <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
        <Route index element={<LazyRoute><DashboardPage /></LazyRoute>} />
        <Route path="/fields" element={<LazyRoute><FieldsPage /></LazyRoute>} />
        <Route path="/fields/:fieldId" element={<LazyRoute><FieldDetailPage /></LazyRoute>} />
        <Route path="/irrigation" element={<LazyRoute><IrrigationPage /></LazyRoute>} />
        <Route path="/about" element={<LazyRoute><AboutPage /></LazyRoute>} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  </>;
}
