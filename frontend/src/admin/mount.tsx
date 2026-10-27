import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";

// The back office, mounted instead of the customer app when the address starts with /admin. It is loaded on demand, so
// customers never download it. The router's basename keeps every route inside the back office relative to /admin.
export function mountAdmin(root: HTMLElement) {
  document.title = "Back office · Cover Founder";
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <QueryClientProvider client={new QueryClient()}>
        <BrowserRouter basename="/admin"><App /></BrowserRouter>
      </QueryClientProvider>
    </React.StrictMode>,
  );
}
