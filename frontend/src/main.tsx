import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { SiteNav } from "./components/SiteNav";
import { DashboardPage } from "./pages/Dashboard";
import { IndexDetailPage } from "./pages/IndexDetail";
import { MetricDetailPage } from "./pages/MetricDetail";
import { SignalsPage } from "./pages/Signals";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SiteNav />
        <Routes>
          <Route path="/" element={<DashboardPage group="market" />} />
          <Route path="/stocks" element={<DashboardPage group="stock" />} />
          <Route path="/index/:target" element={<IndexDetailPage />} />
          <Route path="/metric/:metricId/:target" element={<MetricDetailPage />} />
          <Route path="/signals" element={<SignalsPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
