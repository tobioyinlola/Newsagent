import { useQuery } from "@tanstack/react-query";
import { Route, Routes } from "react-router-dom";
import { api } from "./api/client";

function Home() {
  const me = useQuery({ queryKey: ["me"], queryFn: async () => (await api.GET("/v1/me")).data });
  return (
    <main className="mx-auto max-w-2xl p-4">
      <h1 className="text-2xl font-bold">Newsagent</h1>
      <p className="mt-2 text-slate-600">
        {me.data ? `Signed in to ${me.data.workspace_name}` : "Invite-only pilot. Sign in to continue."}
      </p>
    </main>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}
