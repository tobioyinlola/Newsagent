import React from "react";
import { Composition } from "remotion";
import { InterviewMerge, MergeProps, defaultMergeProps } from "./compositions/InterviewMerge";
import { AnchorFigure } from "./compositions/AnchorFigure";
import { AbsoluteFill, Series } from "remotion";
import { BrandIntro } from "./compositions/BrandIntro";
import { BrandOutro } from "./compositions/BrandOutro";
import { INTRO_SECONDS, OUTRO_SECONDS } from "./compositions/brand";
import { NewsStudio } from "./compositions/NewsStudio";
import { FPS, NewsProps, defaultProps } from "./compositions/types";

const innerFrames = (p: NewsProps) =>
  Math.max(FPS, Math.round((p.anchorDurationSeconds + (p.introClip?.seconds ?? 0) + (p.outroClip?.seconds ?? 0)) * FPS));
const innerMergeFrames = (p: MergeProps) =>
  Math.max(FPS, p.scenes.reduce((n, s) => n + Math.max(1, Math.round(s.seconds * FPS)), 0));
// Every finished video opens with the Cover Founder intro and closes with the outro (props.brandCards).
const cards = (p: { brandCards?: boolean }) => (p.brandCards ? Math.round((INTRO_SECONDS + OUTRO_SECONDS) * FPS) : 0);
const calc = ({ props }: { props: NewsProps }) => ({ durationInFrames: innerFrames(props) + cards(props) });
const calcMerge = ({ props }: { props: MergeProps }) => ({ durationInFrames: innerMergeFrames(props) + cards(props) });

// Wraps a composition: intro, then the video itself (its own clock starts at zero), then the outro.
function withBrandCards<P extends { brandCards?: boolean }>(Inner: React.FC<P>, inner: (p: P) => number): React.FC<P> {
  const Wrapped: React.FC<P> = (p) =>
    p.brandCards ? (
      <AbsoluteFill>
        <Series>
          <Series.Sequence durationInFrames={Math.round(INTRO_SECONDS * FPS)}><BrandIntro /></Series.Sequence>
          <Series.Sequence durationInFrames={inner(p)}><Inner {...p} /></Series.Sequence>
          <Series.Sequence durationInFrames={Math.round(OUTRO_SECONDS * FPS)}><BrandOutro /></Series.Sequence>
        </Series>
      </AbsoluteFill>
    ) : (
      <Inner {...p} />
    );
  return Wrapped;
}
const NewsStudioBranded = withBrandCards(NewsStudio, innerFrames);
const InterviewMergeBranded = withBrandCards(InterviewMerge, innerMergeFrames);

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
    <Composition id="NewsStudio-16x9" component={NewsStudioBranded} width={1920} height={1080} fps={FPS}
      durationInFrames={300} defaultProps={defaultProps} calculateMetadata={calc} />
    <Composition id="NewsStudio-9x16" component={NewsStudioBranded} width={1080} height={1920} fps={FPS}
      durationInFrames={300} defaultProps={defaultProps} calculateMetadata={calc} />
    <Composition id="InterviewMerge-16x9" component={InterviewMergeBranded} width={1920} height={1080} fps={FPS}
      durationInFrames={300} defaultProps={defaultMergeProps} calculateMetadata={calcMerge} />
    <Composition id="InterviewMerge-9x16" component={InterviewMergeBranded} width={1080} height={1920} fps={FPS}
      durationInFrames={300} defaultProps={defaultMergeProps} calculateMetadata={calcMerge} />
  </>
);
