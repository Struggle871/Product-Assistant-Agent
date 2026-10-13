import { useState } from "react";

import { answerKnowledge, type AnswerResponse, type Product, type RetrievalResponse } from "./api";

const statusLabels: Record<RetrievalResponse["answerability"], string> = {
  ANSWERABLE: "资料覆盖当前问题",
  PARTIAL: "需要补充资料或适用条件",
  UNANSWERABLE: "现有资料无法回答",
  MISSING_CONTEXT: "需要确认产品或问题",
  CONFLICTED: "资料存在冲突，需要核对",
};

export function KnowledgeSearch({ products }: { products: Product[] }) {
  const [productId, setProductId] = useState("");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<AnswerResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function search() {
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(await answerKnowledge(query.trim(), productId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "检索失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return <section className="panel">
    <div className="panel-title"><div><h3>产品资料问答</h3><p>确认产品并输入问题，查看有资料依据的回答和引用。资料不足时会提示补充信息。</p></div></div>
    <form onSubmit={(event) => { event.preventDefault(); void search(); }}>
      <div className="form-grid">
        <label>确认产品<select aria-label="确认产品" value={productId} disabled={loading} onChange={(event) => { setProductId(event.target.value); setResult(null); }}>
          <option value="">选择产品</option>
          {products.map((product) => <option key={product.id} value={product.id}>{product.brand} {product.name}</option>)}
        </select></label>
        <label>产品问题<input aria-label="产品问题" maxLength={2000} placeholder="例如：如何恢复出厂设置？" value={query} disabled={loading} onChange={(event) => { setQuery(event.target.value); setResult(null); }} /></label>
      </div>
      {products.length === 0 && <p className="muted">请在知识库管理中初始化目录、导入资料并刷新产品列表。</p>}
      <button className="primary-button" type="submit" disabled={loading || !productId || !query.trim()}>{loading ? "检索中…" : "检索资料"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <div aria-live="polite">
      <h3>{statusLabels[result.answerability]}</h3>
      <p className="evidence-text">{result.answer_text}</p>
      {result.excerpts.map((item, index) => <p key={`${item.chunk_id}-${index}`} className="muted">[{index + 1}] {item.citation}</p>)}
      {result.trace.warnings.length > 0 && <p role="status" className="muted">部分检索或回答能力受限，当前结果可能不完整。请核对下面的资料原文。</p>}
      <p className="muted">检索到 {result.evidence.length} 段资料</p>
      {result.evidence.map((item) => <article className="evidence-card" key={item.chunk_id}>
        <h4>{item.citation}</h4><p className="evidence-text">{item.text}</p>
      </article>)}
    </div>}
  </section>;
}
