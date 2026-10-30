import { Navigate, Route, Routes } from "react-router-dom";
import { Audit } from "./components/admin/Audit";
import { BillingAdmin } from "./components/admin/BillingAdmin";
import { Costs } from "./components/admin/Costs";
import { JobsTab } from "./components/admin/JobsTab";
import { Operations } from "./components/admin/Operations";
import { Review } from "./components/admin/Review";
import { Setup } from "./components/admin/Setup";
import { Layout } from "./components/Layout";
import { RequireOperator } from "./components/RequireOperator";
import { RequirePermission } from "./components/RequirePermission";
import { HOME_ORDER, useCan } from "./lib/can";
import { CustomerDetail, Customers } from "./pages/Customers";
import { Join } from "./pages/Join";
import { Forgot, Login, OtpChallenge } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Presenter } from "./pages/Presenter";
import { DistributionAdmin } from "./pages/Distribution";
import { Revenue } from "./pages/Revenue";
import { Security } from "./pages/Security";
import { TeamPage } from "./pages/Team";

const Page = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <>
    <h1 className="text-2xl font-bold">{title}</h1>
    <div className="space-y-4">{children}</div>
  </>
);

const Guard = ({ any, children }: { any: string[]; children: React.ReactNode }) => <RequirePermission any={any}>{children}</RequirePermission>;

// "/" is the overview; a role without it lands on the first screen it does have.
function Home() {
  const can = useCan();
  const first = HOME_ORDER.find(([, need]) => need.length === 0 || can(...need));
  if (first && first[0] !== "/") return <Navigate to={first[0]} replace />;
  return <Guard any={["overview.view"]}><Overview /></Guard>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/otp" element={<OtpChallenge />} />
      <Route path="/forgot" element={<Forgot />} />
      <Route path="/join" element={<Join />} />
      <Route element={<RequireOperator />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/customers" element={<Guard any={["customers.view"]}><Customers /></Guard>} />
          <Route path="/customers/:id" element={<Guard any={["customers.view"]}><CustomerDetail /></Guard>} />
          <Route path="/revenue" element={<Guard any={["finance.view"]}><Revenue /></Guard>} />
          <Route path="/distribution" element={<Guard any={["operations.view"]}><DistributionAdmin /></Guard>} />
          <Route path="/operations" element={<Guard any={["operations.view"]}><Page title="Operations"><Operations /></Page></Guard>} />
          <Route path="/review" element={<Guard any={["review.manage"]}><Page title="Review queue"><Review /></Page></Guard>} />
          <Route path="/jobs" element={<Guard any={["operations.view"]}><Page title="Jobs"><JobsTab /></Page></Guard>} />
          <Route path="/costs" element={<Guard any={["finance.view"]}><Page title="Costs"><Costs /></Page></Guard>} />
          <Route path="/presenter" element={<Guard any={["presenter.manage"]}><Presenter /></Guard>} />
          <Route path="/billing" element={<Guard any={["finance.view"]}><Page title="Credits and payments"><BillingAdmin /></Page></Guard>} />
          <Route path="/setup" element={<Guard any={["customers.manage", "finance.view"]}><Page title="Setup"><Setup /></Page></Guard>} />
          <Route path="/team" element={<Guard any={["team.manage"]}><TeamPage /></Guard>} />
          <Route path="/audit" element={<Guard any={["audit.view"]}><Page title="Audit log"><Audit /></Page></Guard>} />
          <Route path="/security" element={<Security />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
