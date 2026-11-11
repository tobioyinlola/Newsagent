import { Suspense, lazy, type ComponentType, type ReactNode } from "react";
import { Navigate, Route, Routes, useParams, useLocation } from "react-router-dom";
import { TrackingConsent } from "./components/Analytics";
import { BackButton } from "./components/BackButton";
import { RequireAuth } from "./components/RequireAuth";

// Every page is its own chunk, loaded when it is opened. The founder page (/i/:token) in particular must stay small: a phone on 4G
// downloads as little as possible before the camera starts (e2e-real/interview.spec.ts holds it under 1 MB).
const named = <K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) =>
  lazy(() => load().then((m) => ({ default: m[name] })));

const Founder = lazy(() => import("./founder/Founder"));
const Landing = named(() => import("./pages/Landing"), "Landing");
const Newsroom = named(() => import("./pages/Newsroom"), "Newsroom");
const LatestStories = named(() => import("./pages/LatestStories"), "LatestStories");
const CFNews = named(() => import("./pages/CFNews"), "CFNews");
const StoryPage = named(() => import("./pages/StoryPage"), "StoryPage");
const DistributionPage = named(() => import("./pages/DistributionPage"), "DistributionPage");
const Login = named(() => import("./pages/Login"), "Login");
const Signup = named(() => import("./pages/Login"), "Signup");
const OtpChallenge = named(() => import("./pages/Login"), "OtpChallenge");
const Forgot = named(() => import("./pages/Login"), "Forgot");
const Share = named(() => import("./pages/Share"), "Share");
const MockPay = named(() => import("./pages/Billing"), "MockPay");
const Billing = named(() => import("./pages/Billing"), "Billing");
const Layout = named(() => import("./components/Layout"), "Layout");
const DistributionRequestPage = named(() => import("./pages/DistributionRequest"), "DistributionRequestPage");
const Dashboard = named(() => import("./pages/Dashboard"), "Dashboard");
const Projects = named(() => import("./pages/Projects"), "Projects");
const NewProject = named(() => import("./pages/NewProject"), "NewProject");
const NewProjectClassic = named(() => import("./pages/NewProjectClassic"), "NewProjectClassic");
const ProjectDetail = named(() => import("./pages/ProjectDetail"), "ProjectDetail");
const Brand = named(() => import("./pages/Brand"), "Brand");
const Analytics = named(() => import("./pages/Analytics"), "Analytics");
const CardCheckout = named(() => import("./pages/CardCheckout"), "CardCheckout");
const StripeReturn = named(() => import("./pages/StripeReturn"), "StripeReturn");
const TransferCheckout = named(() => import("./pages/TransferCheckout"), "TransferCheckout");
const BankCheckout = named(() => import("./pages/BankCheckout"), "BankCheckout");
const Settings = named(() => import("./pages/Settings"), "Settings");
const ProfileSettings = named(() => import("./pages/Settings"), "ProfileSettings");
const Security = named(() => import("./pages/Security"), "Security");
const Referrals = named(() => import("./pages/Referrals"), "Referrals");
const TermsPage = named(() => import("./pages/Legal"), "TermsPage");
const PrivacyPage = named(() => import("./pages/Legal"), "PrivacyPage");

const dark = (el: ReactNode) => <Suspense fallback={<div className="min-h-screen bg-ink" />}>{el}</Suspense>;
const plain = (el: ReactNode) => <Suspense fallback={<p className="p-6" role="status">Loading…</p>}>{el}</Suspense>;

function SettingsRedirect({ tab }: { tab: string }) {
  const location = useLocation();
  return <Navigate replace to={`/settings/${tab}${location.search}${location.hash}`} />;
}

// Addresses used before the move to /ai-newsroom, /latest-stories and /press-distribution keep working (emails already sent link to them).
const OldProject = () => <Navigate to={`/ai-newsroom/${useParams().id}`} replace />;

export function App() {
  return (
    <>
    <TrackingConsent />
    <Routes>
      <Route path="/" element={dark(<Landing />)} />
      <Route path="/ai-newsroom" element={dark(<Newsroom />)} />
      <Route path="/press-distribution" element={dark(<DistributionPage />)} />
      <Route path="/latest-stories" element={dark(<LatestStories />)} />
      <Route path="/cf-news" element={dark(<CFNews />)} />
      <Route path="/terms" element={dark(<TermsPage />)} />
      <Route path="/privacy" element={dark(<PrivacyPage />)} />
      <Route path="/latest-stories/:slug" element={dark(<StoryPage />)} />
      <Route path="/newsroom" element={<Navigate to="/ai-newsroom" replace />} />
      <Route path="/distribution" element={<Navigate to="/press-distribution" replace />} />
      <Route path="/projects" element={<Navigate to="/ai-newsroom/videos" replace />} />
      <Route path="/projects/new" element={<Navigate to="/ai-newsroom/new" replace />} />
      <Route path="/projects/new-classic" element={<Navigate to="/ai-newsroom/new-classic" replace />} />
      <Route path="/projects/:id" element={<OldProject />} />
      <Route path="/login" element={plain(<Login />)} />
      <Route path="/signup" element={plain(<Signup />)} />
      <Route path="/otp" element={plain(<OtpChallenge />)} />
      <Route path="/forgot" element={plain(<Forgot />)} />
      <Route path="/s/:token" element={<><div className="px-4 pt-4"><BackButton fallback="/" /></div>{plain(<Share />)}</>} />
      <Route path="/i/:token" element={<><div className="bg-ink px-4 pt-2 text-white"><BackButton fallback="/" /></div>{plain(<Founder />)}</>} />
      <Route path="/billing/pay/:checkoutId" element={<><div className="px-4 pt-4"><BackButton fallback="/settings/billing" /></div>{plain(<MockPay />)}</>} />
      <Route element={<RequireAuth />}>
        <Route element={plain(<Layout />)}>
          <Route path="/distribution/request" element={plain(<DistributionRequestPage />)} />
          <Route path="/referrals" element={plain(<Referrals />)} />
          <Route path="/dashboard" element={plain(<Dashboard />)} />
          <Route path="/ai-newsroom/videos" element={plain(<Projects />)} />
          <Route path="/ai-newsroom/new" element={plain(<NewProject />)} />
          <Route path="/ai-newsroom/new-classic" element={plain(<NewProjectClassic />)} /> {/* the original script-first flow; not linked */}
          <Route path="/ai-newsroom/:id" element={plain(<ProjectDetail />)} />
          <Route path="/brand" element={plain(<Brand />)} />
          <Route path="/analytics" element={plain(<Analytics />)} />
          <Route path="/billing" element={<SettingsRedirect tab="billing" />} />
          <Route path="/billing/card/:checkoutId" element={plain(<CardCheckout />)} />
          <Route path="/billing/stripe/:checkoutId" element={plain(<StripeReturn />)} />
          <Route path="/billing/transfer/:checkoutId" element={plain(<TransferCheckout />)} />
          <Route path="/billing/bank/:checkoutId" element={plain(<BankCheckout />)} />
          <Route path="/account" element={<SettingsRedirect tab="profile" />} />
          <Route path="/security" element={<SettingsRedirect tab="password" />} />
          <Route path="/settings" element={plain(<Settings />)}>
            <Route index element={<Navigate to="profile" replace />} />
            <Route path="profile" element={plain(<ProfileSettings />)} />
            <Route path="password" element={plain(<Security />)} />
            <Route path="billing" element={plain(<Billing />)} />
            <Route path="referral" element={plain(<Referrals />)} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
    </>
  );
}
