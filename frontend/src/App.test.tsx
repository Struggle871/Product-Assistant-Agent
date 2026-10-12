import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { App } from "./App";

vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));

test("renders the product assistant workspace", () => {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <App />
    </QueryClientProvider>,
  );
  expect(screen.getByRole("heading", { name: "产品使用助手" })).toBeInTheDocument();
  expect(screen.getByText("语音转写")).toBeInTheDocument();
});
