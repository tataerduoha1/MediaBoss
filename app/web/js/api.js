/** API 封装：统一错误处理、401 跳登录。 */
export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body, opts = {}) {
  const init = { method, headers: {}, ...opts };
  if (body !== undefined && !(body instanceof FormData)) {
    init.body = JSON.stringify(body);
    init.headers["Content-Type"] = "application/json";
  } else if (body instanceof FormData) {
    init.body = body;
  }
  let res;
  try {
    res = await fetch("/api" + path, init);
  } catch {
    throw new ApiError(0, "网络连接失败");
  }
  let data = null;
  try { data = await res.json(); } catch { /* 空响应 */ }
  if (!res.ok || (data && data.ok === false)) {
    const msg = (data && data.error) || `请求失败 (${res.status})`;
    if (res.status === 401 && !path.startsWith("/auth/")) {
      window.dispatchEvent(new CustomEvent("mb:unauthorized"));
    }
    throw new ApiError(res.status, msg);
  }
  return data && data.data !== undefined ? data.data : data;
}

export const api = {
  get: (p, opts) => request("GET", p, undefined, opts),
  post: (p, body, opts) => request("POST", p, body, opts),
  put: (p, body, opts) => request("PUT", p, body, opts),
  patch: (p, body, opts) => request("PATCH", p, body, opts),
  del: (p, body, opts) => request("DELETE", p, body, opts),
};
