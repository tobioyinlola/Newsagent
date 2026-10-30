import { AudienceReport } from "../../components/AudienceReport";
import { getToken } from "../lib/auth";
import { useCan } from "../lib/can";
export function AnalyticsAdmin() { return <AudienceReport token={getToken()} admin canManage={useCan()("operations.manage")} />; }
