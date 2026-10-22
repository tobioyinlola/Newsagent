import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { Account } from "./pages/Account";
import { Admin } from "./pages/Admin";
import { Billing, MockPay } from "./pages/Billing";
import { Brand } from "./pages/Brand";
import { Login } from "./pages/Login";
import { NewProject } from "./pages/NewProject";
import { ProjectDetail } from "./pages/ProjectDetail";
import { Projects } from "./pages/Projects";
import { Redeem } from "./pages/Redeem";
import { Share } from "./pages/Share";

// The founder page is its own chunk so a phone on 4G downloads as little as possible before the camera starts.
const Founder = lazy(() => import("./founder/Founder"));

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/redeem" element={<Redeem />} />
      <Route path="/s/:token" element={<Share />} />
      <Route path="/i/:token" element={<Suspense fallback={<p className="p-6">Loading…</p>}><Founder /></Suspense>} />
      <Route path="/billing/pay/:checkoutId" element={<MockPay />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/projects" element={<Projects />} />
          <Route path="/projects/new" element={<NewProject />} />
          <Route path="/projects/:id" element={<ProjectDetail />} />
          <Route path="/brand" element={<Brand />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/account" element={<Account />} />
          <Route path="/admin" element={<Admin />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  );
}
