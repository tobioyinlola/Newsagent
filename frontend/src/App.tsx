import { TransferCheckout } from "./pages/TransferCheckout";
import { Referrals } from "./pages/Referrals";
import { Analytics } from "./pages/Analytics";
import { Suspense, lazy } from "react";
import { Navigate, Route, Routes, useParams } from "react-router-dom";
import { Layout } from "./components/Layout";
import { RequireAuth } from "./components/RequireAuth";
import { Account } from "./pages/Account";
import { Security } from "./pages/Security";
import { CardCheckout } from "./pages/CardCheckout";
import { BankCheckout } from "./pages/BankCheckout";
import { Billing, MockPay } from "./pages/Billing";
import { Brand } from "./pages/Brand";
import { Dashboard } from "./pages/Dashboard";
import { Forgot, Login, OtpChallenge, Signup } from "./pages/Login";
import { NewProject } from "./pages/NewProject";
import { NewProjectClassic } from "./pages/NewProjectClassic";
import { ProjectDetail } from "./pages/ProjectDetail";
import { DistributionRequestPage } from "./pages/DistributionRequest";
import { Projects } from "./pages/Projects";
import { Share } from "./pages/Share";

// The founder page is its own chunk so a phone on 4G downloads as little as possible before the camera starts.
const Founder = lazy(() => import("./founder/Founder"));
const Landing = lazy(() => import("./pages/Landing").then((m) => ({ default: m.Landing })));
const Newsroom = lazy(() => import("./pages/Newsroom").then((m) => ({ default: m.Newsroom })));
const LatestStories = lazy(() => import("./pages/LatestStories").then((m) => ({ default: m.LatestStories })));
const StoryPage = lazy(() => import("./pages/StoryPage").then((m) => ({ default: m.StoryPage })));
const DistributionPage = lazy(() => import("./pages/DistributionPage").then((m) => ({ default: m.DistributionPage })));

// Addresses used before the move to /ai-newsroom, /latest-stories and /press-distribution keep working (emails already sent link to them).
const OldProject = () => <Navigate to={`/ai-newsroom/${useParams().id}`} replace />;

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Suspense fallback={<div className="min-h-screen bg-ink" />}><Landing /></Suspense>} />
      <Route path="/ai-newsroom" element={<Suspense fallback={<div className="min-h-screen bg-ink" />}><Newsroom /></Suspense>} />
      <Route path="/press-distribution" element={<Suspense fallback={<div className="min-h-screen bg-ink" />}><DistributionPage /></Suspense>} />
      <Route path="/latest-stories" element={<Suspense fallback={<div className="min-h-screen bg-ink" />}><LatestStories /></Suspense>} />
      <Route path="/latest-stories/:slug" element={<Suspense fallback={<div className="min-h-screen bg-ink" />}><StoryPage /></Suspense>} />
      <Route path="/newsroom" element={<Navigate to="/ai-newsroom" replace />} />
      <Route path="/distribution" element={<Navigate to="/press-distribution" replace />} />
      <Route path="/projects" element={<Navigate to="/ai-newsroom/videos" replace />} />
      <Route path="/projects/new" element={<Navigate to="/ai-newsroom/new" replace />} />
      <Route path="/projects/new-classic" element={<Navigate to="/ai-newsroom/new-classic" replace />} />
      <Route path="/projects/:id" element={<OldProject />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/otp" element={<OtpChallenge />} />
      <Route path="/forgot" element={<Forgot />} />
      <Route path="/s/:token" element={<Share />} />
      <Route path="/i/:token" element={<Suspense fallback={<p className="p-6">Loading…</p>}><Founder /></Suspense>} />
      <Route path="/billing/pay/:checkoutId" element={<MockPay />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/distribution/request" element={<DistributionRequestPage />} />
          <Route path="/referrals" element={<Referrals />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/ai-newsroom/videos" element={<Projects />} />
          <Route path="/ai-newsroom/new" element={<NewProject />} />
          <Route path="/ai-newsroom/new-classic" element={<NewProjectClassic />} /> {/* the original script-first flow; not linked */}
          <Route path="/ai-newsroom/:id" element={<ProjectDetail />} />
          <Route path="/brand" element={<Brand />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/billing/card/:checkoutId" element={<CardCheckout />} />
          <Route path="/billing/transfer/:checkoutId" element={<TransferCheckout />} />
          <Route path="/billing/bank/:checkoutId" element={<BankCheckout />} />
          <Route path="/account" element={<Account />} />
          <Route path="/security" element={<Security />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
