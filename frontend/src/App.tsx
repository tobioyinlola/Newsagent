import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { Account } from "./pages/Account";
import { Security } from "./pages/Security";
import { Billing, MockPay } from "./pages/Billing";
import { Brand } from "./pages/Brand";
import { Dashboard } from "./pages/Dashboard";
import { Forgot, Login, OtpChallenge, Signup } from "./pages/Login";
import { NewProject } from "./pages/NewProject";
import { NewProjectClassic } from "./pages/NewProjectClassic";
import { ProjectDetail } from "./pages/ProjectDetail";
import { Projects } from "./pages/Projects";
import { Share } from "./pages/Share";

// The founder page is its own chunk so a phone on 4G downloads as little as possible before the camera starts.
const Founder = lazy(() => import("./founder/Founder"));
const Landing = lazy(() => import("./pages/Landing").then((m) => ({ default: m.Landing })));

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Suspense fallback={<div className="min-h-screen bg-ink" />}><Landing /></Suspense>} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/otp" element={<OtpChallenge />} />
      <Route path="/forgot" element={<Forgot />} />
      <Route path="/s/:token" element={<Share />} />
      <Route path="/i/:token" element={<Suspense fallback={<p className="p-6">Loading…</p>}><Founder /></Suspense>} />
      <Route path="/billing/pay/:checkoutId" element={<MockPay />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/new" element={<NewProject />} />
          <Route path="/projects/new-classic" element={<NewProjectClassic />} /> {/* the original script-first flow; not linked */}
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/brand" element={<Brand />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/account" element={<Account />} />
          <Route path="/security" element={<Security />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
