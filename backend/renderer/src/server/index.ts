import { createApp } from "./app";
import { sweepTemp } from "./tmpsweep";

const secret = process.env.RENDERER_SHARED_SECRET || "";
if (!secret) throw new Error("RENDERER_SHARED_SECRET is required");
const port = Number(process.env.PORT || 4000);
const app = createApp({ secret });
const server = app.listen(port, () => console.log(JSON.stringify({ msg: "renderer listening", port })));
// A deploy or restart sends SIGTERM: stop taking new work, give what is running a short while to finish, then exit.
let stopping = false;
const stop = () => {
  if (stopping) return;
  stopping = true;
  app.locals.drain();
  console.log(JSON.stringify({ msg: "renderer draining" }));
  const deadline = Date.now() + Number(process.env.RENDER_DRAIN_SECONDS ?? 20) * 1000;
  const tick = setInterval(() => {
    if (app.locals.idle() || Date.now() > deadline) { clearInterval(tick); server.close(); process.exit(0); }
  }, 500);
};
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
const sweep = () => { const n = sweepTemp(); if (n) console.log(JSON.stringify({ msg: "removed abandoned scratch directories", count: n })); };
sweep();
setInterval(sweep, 3600 * 1000).unref();
