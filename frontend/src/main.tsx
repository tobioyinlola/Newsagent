import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./index.css";

const root = document.getElementById("root")!;
if (location.pathname === "/admin" || location.pathname.startsWith("/admin/")) {
  // the operator back office: a separate chunk, loaded only here
  void import("./admin/mount").then((m) => m.mountAdmin(root));
} else {
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <QueryClientProvider client={new QueryClient()}>
        <BrowserRouter><App /></BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
