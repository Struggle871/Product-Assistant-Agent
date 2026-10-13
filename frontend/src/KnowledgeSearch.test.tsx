import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { KnowledgeSearch } from "./KnowledgeSearch";
import { answerKnowledge, type Product } from "./api";

vi.mock("./api", () => ({ answerKnowledge: vi.fn() }));
afterEach(() => vi.clearAllMocks());

const products: Product[] = [{ id: "product", brand: "TP-Link", name: "AX55", category: "router", aliases: [], models: [] }];

test("requires a product and a non-empty question before searching", () => {
  render(<KnowledgeSearch products={products} />);
  expect(screen.getByRole("button", { name: "检索资料" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("确认产品"), { target: { value: "product" } });
  fireEvent.change(screen.getByLabelText("产品问题"), { target: { value: " " } });
  expect(screen.getByRole("button", { name: "检索资料" })).toBeDisabled();
});

test("renders assessment, citations and partial service warning", async () => {
  vi.mocked(answerKnowledge).mockResolvedValue({
    answer_text: "需要补充版本资料", excerpts: [], model: "test", prompt_version: "test", model_latency_ms: 1,
    answerability: "PARTIAL", answerability_reasons: ["需要补充版本资料"],
    evidence: [{ chunk_id: "chunk", document_id: "doc", document_version_id: "v1", text: "原文证据", heading: "重置", page_number: 2, product_id: "product", document_title: "Manual", citation: "Manual · 第 2 页 · 重置", rrf_score: 0.01 }],
    trace: { vector_candidates: 0, bm25_candidates: 1, total_latency_ms: 3, warnings: ["timeout"], embedding_profile: "test" },
  });
  render(<KnowledgeSearch products={products} />);
  fireEvent.change(screen.getByLabelText("确认产品"), { target: { value: "product" } });
  fireEvent.change(screen.getByLabelText("产品问题"), { target: { value: " 如何重置？ " } });
  fireEvent.click(screen.getByRole("button", { name: "检索资料" }));
  expect(await screen.findByText("需要补充资料或适用条件")).toBeInTheDocument();
  expect(screen.getByText("Manual · 第 2 页 · 重置")).toBeInTheDocument();
  expect(screen.getByText("原文证据")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("部分检索或回答能力受限");
  expect(answerKnowledge).toHaveBeenCalledWith("如何重置？", "product");
});

test("shows request failure and permits retry", async () => {
  vi.mocked(answerKnowledge).mockRejectedValue(new Error("服务暂时不可用"));
  render(<KnowledgeSearch products={products} />);
  fireEvent.change(screen.getByLabelText("确认产品"), { target: { value: "product" } });
  fireEvent.change(screen.getByLabelText("产品问题"), { target: { value: "如何重置？" } });
  fireEvent.click(screen.getByRole("button", { name: "检索资料" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("服务暂时不可用");
  await waitFor(() => expect(screen.getByRole("button", { name: "检索资料" })).toBeEnabled());
});
