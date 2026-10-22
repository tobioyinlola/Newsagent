import React from "react";
import { Composition } from "remotion";
import { InterviewMerge, MergeProps, defaultMergeProps } from "./compositions/InterviewMerge";
import { NewsStudio } from "./compositions/NewsStudio";
import { FPS, NewsProps, defaultProps } from "./compositions/types";

const calc = ({ props }: { props: NewsProps }) => ({
  durationInFrames: Math.max(FPS, Math.round(props.anchorDurationSeconds * FPS)),
});

const calcMerge = ({ props }: { props: MergeProps }) => ({
  durationInFrames: Math.max(FPS, props.scenes.reduce((n, s) => n + Math.max(1, Math.round(s.seconds * FPS)), 0)),
});

export const Root: React.FC = () => (
  <>
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
