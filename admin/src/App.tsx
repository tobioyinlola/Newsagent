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
import { CustomerDetail, Customers } from "./pages/Customers";
import { Forgot, Login, OtpChallenge } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Presenter } from "./pages/Presenter";
import { Revenue } from "./pages/Revenue";
import { Security } from "./pages/Security";

const Page = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <>
    <h1 className="text-2xl font-bold">{title}</h1>
    <div className="space-y-4">{children}</div>
  </>
);

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/otp" element={<OtpChallenge />} />
      <Route path="/forgot" element={<Forgot />} />
      <Route element={<RequireOperator />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Overview />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/customers/:id" element={<CustomerDetail />} />
          <Route path="/revenue" element={<Revenue />} />
          <Route path="/operations" element={<Page title="Operations"><Operations /></Page>} />
          <Route path="/review" element={<Page title="Review queue"><Review /></Page>} />
          <Route path="/jobs" element={<Page title="Jobs"><JobsTab /></Page>} />
          <Route path="/costs" element={<Page title="Costs"><Costs /></Page>} />
          <Route path="/presenter" element={<Presenter />} />
          <Route path="/billing" element={<Page title="Credit packs and payments"><BillingAdmin /></Page>} />
          <Route path="/setup" element={<Page title="Setup"><Setup /></Page>} />
          <Route path="/audit" element={<Page title="Audit log"><Audit /></Page>} />
          <Route path="/security" element={<Security />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
