import { createApp } from "./app";

const secret = process.env.RENDERER_SHARED_SECRET || "";
if (!secret) throw new Error("RENDERER_SHARED_SECRET is required");
const port = Number(process.env.PORT || 4000);
createApp({ secret }).listen(port, () => console.log(JSON.stringify({ msg: "renderer listening", port })));
