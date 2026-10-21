import { AbsoluteFill, useCurrentFrame } from "remotion";
export const Floor = () => <AbsoluteFill style={{ background: "#123", color: "#fff", fontSize: 80 }}>{useCurrentFrame()}</AbsoluteFill>;
