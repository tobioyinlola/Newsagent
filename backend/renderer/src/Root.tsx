import React from "react";
import { AbsoluteFill, Composition } from "remotion";
import { InterviewMerge, MergeProps, defaultMergeProps } from "./compositions/InterviewMerge";
import { AnchorFigure } from "./compositions/AnchorFigure";
import { BrandIntro, INTRO_SECONDS } from "./compositions/BrandIntro";
import { BrandOutro, OUTRO_SECONDS } from "./compositions/BrandOutro";
import { NewsStudio } from "./compositions/NewsStudio";
import { FPS, NewsProps, defaultProps } from "./compositions/types";

const calc = ({ props }: { props: NewsProps }) => ({
  durationInFrames: Math.max(
    FPS,
    Math.round((props.anchorDurationSeconds + (props.introClip?.seconds ?? 0) + (props.outroClip?.seconds ?? 0)) * FPS),
  ),
});

const calcMerge = ({ props }: { props: MergeProps }) => ({
  durationInFrames: Math.max(FPS, props.scenes.reduce((n, s) => n + Math.max(1, Math.round(s.seconds * FPS)), 0)),
});

// The stand-in presenter on its own, for rendering a transparent clip that plays the part of the avatar vendor's video.
const StandInAnchor: React.FC = () => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end" }}>
    <AnchorFigure height="100%" />
  </AbsoluteFill>
);

export const Root: React.FC = () => (
  <>
    {/* preview only: the branded opening and closing cards, not used by any video yet */}
    <Composition id="BrandIntro" component={BrandIntro} width={1920} height={1080} fps={FPS} durationInFrames={INTRO_SECONDS * FPS} />
    <Composition id="BrandOutro" component={BrandOutro} width={1920} height={1080} fps={FPS} durationInFrames={OUTRO_SECONDS * FPS} />
    <Composition id="StandInAnchor" component={StandInAnchor} width={640} height={720} fps={FPS} durationInFrames={FPS * 30} />
    <Composition id="NewsStudio-16x9" component={NewsStudio} width={1920} height={1080} fps={FPS}
      durationInFrames={300} defaultProps={defaultProps} calculateMetadata={calc} />
    <Composition id="NewsStudio-9x16" component={NewsStudio} width={1080} height={1920} fps={FPS}
      durationInFrames={300} defaultProps={defaultProps} calculateMetadata={calc} />
    <Composition id="InterviewMerge-16x9" component={InterviewMerge} width={1920} height={1080} fps={FPS}
      durationInFrames={300} defaultProps={defaultMergeProps} calculateMetadata={calcMerge} />
    <Composition id="InterviewMerge-9x16" component={InterviewMerge} width={1080} height={1920} fps={FPS}
      durationInFrames={300} defaultProps={defaultMergeProps} calculateMetadata={calcMerge} />
  </>
);
