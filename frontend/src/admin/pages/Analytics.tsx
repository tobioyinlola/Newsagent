import { AudienceReport } from "../../components/AudienceReport";
import { SiteVisits } from "../components/SiteVisits";
import { getToken } from "../lib/auth";
import { useCan } from "../lib/can";
export function AnalyticsAdmin() { return <><SiteVisits /><AudienceReport token={getToken()} admin canManage={useCan()("operations.manage")} /></>; }
