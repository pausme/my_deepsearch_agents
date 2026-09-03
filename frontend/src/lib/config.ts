// API 地址解析优先级：
// 1. 构建时注入 VITE_API_BASE_URL（前后端分离部署时使用）
// 2. 默认走同源（FastAPI/nginx 托管前端静态文件的单进程部署）
// 生产构建不要写死 localhost，否则换机器访问时请求会打到用户自己的本机
function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

const configuredApiBaseUrl = stripTrailingSlash(
  (import.meta.env.VITE_API_BASE_URL || "").trim()
);

export const API_BASE_URL = configuredApiBaseUrl;

function sameOriginWsBaseUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}`;
}

function deriveWsBaseUrl(apiBaseUrl: string): string {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return stripTrailingSlash(import.meta.env.VITE_WS_BASE_URL.trim());
  }

  if (apiBaseUrl.startsWith("https://")) {
    return apiBaseUrl.replace(/^https:\/\//, "wss://");
  }

  if (apiBaseUrl.startsWith("http://")) {
    return apiBaseUrl.replace(/^http:\/\//, "ws://");
  }

  // API 未配置或为同源/相对路径时，WebSocket 跟随当前页面域名
  return sameOriginWsBaseUrl();
}

export const WS_BASE_URL = deriveWsBaseUrl(API_BASE_URL);
