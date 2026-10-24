import { createApp } from "./app";
import { sweepTemp } from "./tmpsweep";

const secret = process.env.RENDERER_SHARED_SECRET || "";
if (!secret) throw new Error("RENDERER_SHARED_SECRET is required");
const port = Number(process.env.PORT || 4000);
createApp({ secret }).listen(port, () => console.log(JSON.stringify({ msg: "renderer listening", port })));
const sweep = () => { const n = sweepTemp(); if (n) console.log(JSON.stringify({ msg: "removed abandoned scratch directories", count: n })); };
sweep();
setInterval(sweep, 3600 * 1000).unref();
