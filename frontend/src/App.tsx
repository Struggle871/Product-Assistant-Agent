import { useEffect, useMemo, useState } from "react";
import { Activity, Archive, Database, FilePlus2, KeyRound, RefreshCw, Server, Settings2, Upload } from "lucide-react";

import { adminApi, getReadiness, type Document, type IndexVersion, type Job, type Product, type TrustedSource } from "./api";
import "./styles.css";

type View = "assistant" | "knowledge";
const statusLabel: Record<string, string> = { READY: "可检索", FAILED: "失败", ARCHIVED: "已归档", UPLOADED: "待处理", PARSING: "解析中", CHUNKING: "切片中", QUEUED: "排队中", RUNNING: "处理中", SUCCEEDED: "成功" };

export function App() {
  const [view, setView] = useState<View>("knowledge");
  const [apiKey, setApiKey] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [sources, setSources] = useState<TrustedSource[]>([]);
  const [indexes, setIndexes] = useState<IndexVersion[]>([]);
  const [selectedProduct, setSelectedProduct] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [selectedVersion, setSelectedVersion] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [readiness, setReadiness] = useState<{ status: string } | null>(null);
  const selected = products.find((product) => product.id === selectedProduct);
  const model = selected?.models.find((item) => item.id === selectedModel);
  const latestIndex = indexes.find((item) => item.status === "PUBLISHED");
  const activeJobs = useMemo(() => jobs.filter((job) => ["QUEUED", "RUNNING"].includes(job.status)).length, [jobs]);

  async function refresh(key = apiKey) {
    if (!key) return;
    setLoading(true);
    try {
      const [nextProducts, nextDocuments, nextJobs, nextSources, nextIndexes] = await Promise.all([adminApi.products(key), adminApi.documents(key), adminApi.jobs(key), adminApi.sources(key), adminApi.indexes(key)]);
      setProducts(nextProducts); setDocuments(nextDocuments); setJobs(nextJobs); setSources(nextSources); setIndexes(nextIndexes); setNotice("知识库状态已刷新");
    } catch (error) { setNotice(error instanceof Error ? error.message : "刷新失败"); } finally { setLoading(false); }
  }
  useEffect(() => { void getReadiness().then((result) => setReadiness(result)).catch(() => setReadiness(null)); }, []);
  async function seed() {
    setLoading(true);
    try { const result = await adminApi.seed(apiKey); setNotice(`目录已初始化：${result.products} 个产品，${result.trusted_sources} 个可信来源`); await refresh(); } catch (error) { setNotice(error instanceof Error ? error.message : "初始化失败"); } finally { setLoading(false); }
  }
  async function upload() {
    if (!file || !selectedProduct) { setNotice("请先选择产品并添加资料文件"); return; }
    const form = new FormData(); form.append("file", file); form.append("product_id", selectedProduct); if (selectedModel) form.append("product_model_id", selectedModel); if (selectedVersion) form.append("product_version_id", selectedVersion);
    setLoading(true);
    try { await adminApi.upload(apiKey, form); setFile(null); setNotice("资料已提交，入库任务已排队"); await refresh(); } catch (error) { setNotice(error instanceof Error ? error.message : "上传失败"); } finally { setLoading(false); }
  }
  async function action(actionFn: () => Promise<unknown>, success: string) { try { await actionFn(); setNotice(success); await refresh(); } catch (error) { setNotice(error instanceof Error ? error.message : "操作失败"); } }

  return <main className="app-shell"><header className="topbar"><div className="brand"><span className="brand-mark">PA</span><div><h1>产品使用助手</h1><p>多模态产品知识与故障排查</p></div></div><div className={`service-state ${readiness?.status === "ready" ? "is-ready" : ""}`}><Activity size={16} />{readiness?.status === "ready" ? "服务已就绪" : "服务检查中"}</div></header>
    <div className="layout"><aside className="sidebar"><div className="side-title">工作区</div><button className={view === "assistant" ? "nav-item active" : "nav-item"} onClick={() => setView("assistant")}><Settings2 size={17} />助手对话</button><button className={view === "knowledge" ? "nav-item active" : "nav-item"} onClick={() => setView("knowledge")}><Database size={17} />知识库管理</button><div className="side-foot"><Server size={16} />{readiness?.status === "ready" ? "依赖服务正常" : "依赖服务待检查"}</div></aside>
      <section className="content"><div className="page-heading"><div><span className="eyebrow">{view === "knowledge" ? "知识工程" : "助手工作台"}</span><h2>{view === "knowledge" ? "产品知识库" : "产品使用助手"}</h2><p>{view === "knowledge" ? "管理产品目录、可信来源与可检索资料。" : "图片、语音与产品文档将在此处汇聚为可验证的回答。"}</p></div><div className="header-actions"><label className="key-field"><KeyRound size={15} /><input type="password" placeholder="管理 API Key" value={apiKey} onChange={(event) => setApiKey(event.target.value)} /></label><button className="icon-button" title="刷新数据" onClick={() => void refresh()} disabled={!apiKey || loading}><RefreshCw size={17} /></button></div></div>
        {view === "assistant" ? <div className="empty-state"><Settings2 size={28} /><h3>助手对话将在后续阶段接入</h3><p>当前阶段先完成可重复的产品目录与知识入库链路。</p></div> : <><div className="metric-grid"><div className="metric"><span>产品</span><strong>{products.length}</strong></div><div className="metric"><span>资料</span><strong>{documents.length}</strong></div><div className="metric"><span>处理中</span><strong>{activeJobs}</strong></div><div className="metric"><span>活动索引</span><strong>{latestIndex?.chunk_count ?? 0}<small> chunks</small></strong></div></div><div className="toolbar"><button className="primary-button" onClick={() => void seed()} disabled={!apiKey || loading}><Database size={16} />初始化演示目录</button><button className="secondary-button" onClick={() => void refresh()} disabled={!apiKey || loading}><RefreshCw size={16} />刷新</button>{notice && <span className="notice">{notice}</span>}</div>
          <div className="admin-grid"><section className="panel"><div className="panel-title"><div><h3>导入资料</h3><p>支持 Markdown、HTML、TXT、PDF，PDF 文本不足时启动 OCR。</p></div><Upload size={20} /></div><div className="form-grid"><label>产品<select value={selectedProduct} onChange={(event) => { setSelectedProduct(event.target.value); setSelectedModel(""); setSelectedVersion(""); }}><option value="">选择产品</option>{products.map((product) => <option value={product.id} key={product.id}>{product.brand} {product.name}</option>)}</select></label><label>型号<select value={selectedModel} onChange={(event) => { setSelectedModel(event.target.value); setSelectedVersion(""); }} disabled={!selected}><option value="">全部型号</option>{selected?.models.map((item) => <option value={item.id} key={item.id}>{item.model}</option>)}</select></label><label>版本<select value={selectedVersion} onChange={(event) => setSelectedVersion(event.target.value)} disabled={!model}><option value="">全部版本</option>{model?.versions.map((item) => <option value={item.id} key={item.id}>{item.version} {item.platform ?? ""}</option>)}</select></label><label className="file-picker">资料文件<input type="file" accept=".md,.markdown,.html,.htm,.txt,.pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /><span>{file?.name ?? "选择文件"}</span></label></div><button className="primary-button" onClick={() => void upload()} disabled={!apiKey || !file || !selectedProduct || loading}><FilePlus2 size={16} />提交入库</button></section>
          <section className="panel"><div className="panel-title"><div><h3>可信来源</h3><p>联网检索只允许使用已注册的官方域名。</p></div><KeyRound size={20} /></div><ul className="source-list">{sources.map((source) => <li key={source.id}><span><strong>{source.brand}</strong><small>{source.canonical_host}</small></span><em className={source.enabled ? "tag good" : "tag"}>{source.enabled ? "已启用" : "已停用"}</em></li>)}{sources.length === 0 && <li className="muted">初始化目录后显示可信来源</li>}</ul></section></div>
          <section className="panel table-panel"><div className="panel-title"><div><h3>资料与入库任务</h3><p>失败任务可重试，已归档资料不会进入活动索引。</p></div><Archive size={20} /></div><div className="table-wrap"><table><thead><tr><th>资料</th><th>产品</th><th>状态</th><th>任务</th><th>操作</th></tr></thead><tbody>{documents.map((document) => { const job = jobs.find((item) => item.document_id === document.id); const product = products.find((item) => item.id === document.product_id); return <tr key={document.id}><td><strong>{document.title}</strong><small>{document.document_type} · {document.language}</small></td><td>{product ? `${product.brand} ${product.name}` : document.product_id.slice(0, 8)}</td><td><span className={`tag ${document.status === "READY" ? "good" : document.status === "FAILED" ? "bad" : ""}`}>{statusLabel[document.status] ?? document.status}</span></td><td>{job ? statusLabel[job.status] ?? job.status : "-"}</td><td className="row-actions">{job?.status === "FAILED" && <button className="text-button" onClick={() => void action(() => adminApi.retry(apiKey, job.id), "任务已重新排队")}>重试</button>}{document.status !== "ARCHIVED" && <button className="text-button danger" onClick={() => void action(() => adminApi.archive(apiKey, document.id), "资料已归档")}>归档</button>}</td></tr>; })}{documents.length === 0 && <tr><td colSpan={5} className="muted">暂无资料，请先初始化目录并上传文档。</td></tr>}</tbody></table></div></section>
          <section className="panel table-panel"><div className="panel-title"><div><h3>索引版本</h3><p>只有成功完成解析和切片的 READY 资料会参与发布。</p></div><Database size={20} /></div><div className="index-list">{indexes.map((index) => <div className="index-row" key={index.id}><span><strong>{index.version}</strong><small>{index.document_count} documents · {index.chunk_count} chunks</small></span><em className={`tag ${index.status === "PUBLISHED" ? "good" : ""}`}>{index.status === "PUBLISHED" ? "活动" : "已归档"}</em></div>)}{indexes.length === 0 && <div className="muted">完成首次入库后生成索引版本。</div>}</div></section></>}</section></div></main>;
}
