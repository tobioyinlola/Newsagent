import { AudienceReport } from "../components/AudienceReport";
import { getToken } from "../lib/auth";
export function Analytics() { return <AudienceReport token={getToken()} />; }
