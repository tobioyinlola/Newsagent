import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";

// The newsroom behind the house presenters: a softly out-of-focus, dark-blue newsroom with desks and screens. It is the
// same set the male reporter (Marcus) sits in, so every house presenter looks to be in one studio. It is used for a presenter
// whose video arrives as a transparent cut-out (not as a picture that already contains its own studio).
// public/newsroom-plate.jpg is that room with the reporter taken out; its two signs are blurred so nothing in it can be read.
export const NEWSROOM_PLATE = "newsroom-plate.jpg";

export const NewsroomPlate: React.FC = () => (
  <AbsoluteFill style={{ background: "#0a1a3a" }}>
    <Img src={staticFile(NEWSROOM_PLATE)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
  </AbsoluteFill>
);
