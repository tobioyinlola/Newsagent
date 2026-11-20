import { api, unwrap } from "../api/client";
import type { TourBackend, TourProgressMap } from "../components/tour/tourTypes";

export type Choice = { key: string; label: string };
export type Profile = { contact_name?: string; role?: string; phone?: string; website?: string; company_size?: string; goals?: string[]; heard_from?: string; heard_detail?: string };
export type OnboardingState = {
  profile_status: "not_started" | "pending" | "in_progress" | "done" | "skipped";
  profile_step: number;
  profile: Profile;
  tours: TourProgressMap;
  options: { roles: Choice[]; sizes: Choice[]; goals: Choice[]; heard: Choice[]; steps: string[] };
};
export type ProfilePatch = { answers?: Profile; step?: number; status?: "in_progress" | "done" | "skipped" };

export const ONBOARDING_KEY = ["onboarding"];
export const loadOnboarding = async () => (await unwrap(api.GET("/v1/me/onboarding"))) as unknown as OnboardingState;
export const saveProfile = async (body: ProfilePatch) => (await unwrap(api.PUT("/v1/me/onboarding/profile", { body: body as never }))) as unknown as OnboardingState;
export const saveTour = async (id: string, body: { step?: number; done?: boolean; dismissed?: boolean; reset?: boolean }) =>
  (await unwrap(api.PUT("/v1/me/tours/{tour_id}", { params: { path: { tour_id: id } }, body: body as never }))) as unknown as OnboardingState;

/** Tour progress for the customer app. */
export const customerTourBackend: TourBackend = {
  load: async () => (await loadOnboarding()).tours ?? {},
  save: async (id, patch) => (await saveTour(id, patch)).tours ?? {},
};
