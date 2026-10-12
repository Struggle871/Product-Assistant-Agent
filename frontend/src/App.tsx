import { useQuery } from "@tanstack/react-query";
import { Activity, FileText, Image, Mic, Search, Server } from "lucide-react";

import { getReadiness } from "./api";
import "./styles.css";

const capabilities = [
  { icon: Image, label: "图片识别" },
  { icon: Mic, label: "语音转写" },
  { icon: FileText, label: "知识库检索" },
  { icon: Search, label: "官方资料搜索" },
];

export function App() {
  const readiness = useQuery({
    queryKey: ["readiness"],
    queryFn: getReadiness,
    retry: false,
    refetchInterval: 15_000,
  });

  const isReady = readiness.data?.status === "ready";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">PA</span>
          <div>
            <h1>产品使用助手</h1>
            <p>多模态产品知识与故障排查</p>
          </div>
        </div>
        <div className={`service-state ${isReady ? "is-ready" : ""}`}>
          <Activity size={16} aria-hidden="true" />
          {readiness.isPending
            ? "正在检查服务"
            : isReady
              ? "服务已就绪"
              : "基础服务未就绪"}
        </div>
      </header>

      <section className="workspace" aria-labelledby="workspace-title">
        <div className="workspace-header">
          <div>
            <span className="eyebrow">工程骨架</span>
            <h2 id="workspace-title">Agent 工作台</h2>
            <p>阶段一已建立前后端、任务队列、数据与对象存储的运行基础。</p>
          </div>
          <Server size={28} aria-hidden="true" />
        </div>

        <div className="capability-grid">
          {capabilities.map(({ icon: Icon, label }) => (
            <div className="capability" key={label}>
              <Icon size={20} aria-hidden="true" />
              <span>{label}</span>
              <small>待业务阶段接入</small>
            </div>
          ))}
        </div>

        <div className="dependency-panel">
          <h3>基础服务</h3>
          {readiness.isError ? (
            <p className="error">无法连接 API，请确认后端已启动。</p>
          ) : (
            <ul>
              {Object.entries(readiness.data?.dependencies ?? {}).map(([name, value]) => (
                <li key={name}>
                  <span>{name}</span>
                  <strong className={value.status === "ok" ? "ok" : "error"}>
                    {value.status === "ok" ? "正常" : value.detail}
                  </strong>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
