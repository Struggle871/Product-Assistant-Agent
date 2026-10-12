import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { App } from "./App";

vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));

test("renders the product assistant workspace", () => {
  render(
    <App />,
  );
  expect(screen.getByRole("heading", { name: "产品使用助手" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "知识库管理" })).toBeInTheDocument();
  expect(screen.getByPlaceholderText("管理 API Key")).toBeInTheDocument();
});
