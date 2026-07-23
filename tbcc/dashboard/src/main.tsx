import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { ApiTargetProvider } from "./context/ApiTargetContext";
import { DashboardGildedProvider } from "./context/DashboardGildedContext";
import { DashboardThemeProvider } from "./context/DashboardThemeContext";
import { applyGildedSettings, readGildedSettings } from "./utils/dashboardGildedSettings";
import "./index.css";
import "./theme.css";

applyGildedSettings(readGildedSettings());

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ApiTargetProvider>
        <DashboardGildedProvider>
          <DashboardThemeProvider>
            <App />
          </DashboardThemeProvider>
        </DashboardGildedProvider>
      </ApiTargetProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
