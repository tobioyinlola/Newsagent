import React from "react";
import { Composition } from "remotion";
import { NewsStudio } from "./compositions/NewsStudio";
import { FPS, NewsProps, defaultProps } from "./compositions/types";

const calc = ({ props }: { props: NewsProps }) => ({
  durationInFrames: Math.max(FPS, Math.round(props.anchorDurationSeconds * FPS)),
});

export const Root: React.FC = () => (
  <>
    <Composition id="NewsStudio-16x9" component={NewsStudio} width={1920} height={1080} fps={FPS}
      durationInFrames={300} defaultProps={defaultProps} calculateMetadata={calc} />
    <Composition id="NewsStudio-9x16" component={NewsStudio} width={1080} height={1920} fps={FPS}
      durationInFrames={300} defaultProps={defaultProps} calculateMetadata={calc} />
  </>
);
