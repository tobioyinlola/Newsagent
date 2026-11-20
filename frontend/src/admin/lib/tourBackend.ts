import { api, unwrap } from "../api/client";
import type { TourBackend, TourProgressMap } from "../../components/tour/tourTypes";

type State = { tours?: TourProgressMap };
/** Guided-tour progress for the back office: kept on the server per person, so it follows them between devices. */
export const adminTourBackend: TourBackend = {
  load: async () => ((await unwrap(api.GET("/v1/me/onboarding"))) as unknown as State).tours ?? {},
  save: async (id, patch) =>
    ((await unwrap(api.PUT("/v1/me/tours/{tour_id}", { params: { path: { tour_id: id } }, body: patch as never }))) as unknown as State).tours ?? {},
};
