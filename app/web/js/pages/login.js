/** 登录页 */
import { api } from "../api.js?v=4";
import { h } from "../util.js?v=4";

export async function render(root) {
  document.title = "登录 · MediaBoss";
  const err = h("div", { class: "err" });
  const pwd = h("input", { class: "input", type: "password", placeholder: "默认密码 admin", autofocus: "" });
  const btn = h("button", { class: "btn primary" }, "登 录");

  const doLogin = async () => {
    btn.disabled = true;
    btn.textContent = "登录中…";
    err.textContent = "";
    try {
      await api.post("/auth/login", { password: pwd.value });
      location.hash = "#/";
    } catch (e) {
      err.textContent = e.message;
      btn.disabled = false;
      btn.textContent = "登 录";
    }
  };
  pwd.addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
  btn.addEventListener("click", doLogin);

  root.innerHTML = "";
  root.append(h("div", { class: "login-wrap" },
    h("div", { class: "login-card" },
      h("div", { class: "lgo" }, h("span", { class: "mark" }, "▶"), h("h1", {}, "MediaBoss")),
      h("div", { class: "sub" }, "本地视频媒体库 · 私有部署 · 零依赖"),
      h("div", { class: "field" }, h("label", {}, "访问密码"), pwd),
      err,
      btn,
    ),
  ));
  pwd.focus();
}
