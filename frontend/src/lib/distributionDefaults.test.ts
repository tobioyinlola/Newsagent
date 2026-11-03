import { describe, expect, it } from "vitest";
import { latestStoryStart } from "./distribution";

const stories = [
  { project_id: "newest", headline: "Newest headline", announcement: "Newest announcement." },
  { project_id: "older", headline: "Older headline", announcement: "Older announcement." },
];

describe("a new distribution request starts from the most recent story", () => {
  it("picks the newest story and fills in its headline and announcement", () => {
    expect(latestStoryStart(stories, [])).toEqual({
      announcement_source: "platform", story_project_id: "newest", headline: "Newest headline", announcement: "Newest announcement.", project_id: null,
    });
  });
  it("attaches that story's video when it has a finished one, and never another story's video", () => {
    expect(latestStoryStart(stories, [{ id: "newest" }, { id: "older" }])?.project_id).toBe("newest");
    expect(latestStoryStart(stories, [{ id: "older" }])?.project_id).toBeNull(); // the newest story has no finished video: send the story alone
  });
  it("starts empty, for the owner's own story, when there are no stories yet", () => {
    expect(latestStoryStart([], [{ id: "x" }])).toBeNull();
    expect(latestStoryStart(undefined, undefined)).toBeNull();
  });
});
