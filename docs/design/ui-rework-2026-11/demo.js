// Demo wiring: view switching ([data-go] -> [data-view]), role + theme toggles.
const $$ = (s) => document.querySelectorAll(s);
function go(view) {
  $$("[data-view]").forEach((v) => (v.hidden = v.dataset.view !== view));
  $$("[data-go]").forEach((b) => b.toggleAttribute("aria-current", b.dataset.go === view));
}
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-go]");
  if (t) { e.preventDefault(); go(t.dataset.go); }
  const d = e.target.closest("[data-toggle]");
  if (d) document.getElementById(d.dataset.toggle).toggleAttribute("open");
});
const demo = document.createElement("div");
demo.className = "demo";
demo.innerHTML = `<a href="index.html">All</a>
  <button id="r-admin" aria-pressed="true">Admin</button><button id="r-user" aria-pressed="false">User</button>
  <button id="theme">Light / dark</button>`;
document.body.append(demo);
const setRole = (admin) => {
  document.body.classList.toggle("user-view", !admin);
  r_admin.setAttribute("aria-pressed", admin); r_user.setAttribute("aria-pressed", !admin);
  if (!admin && document.querySelector("[data-view]:not([hidden]).admin-only")) go("home");
};
const r_admin = demo.querySelector("#r-admin"), r_user = demo.querySelector("#r-user");
r_admin.onclick = () => setRole(true); r_user.onclick = () => setRole(false);
demo.querySelector("#theme").onclick = () => document.documentElement.classList.toggle("dark");
const p = new URLSearchParams(location.search);
if (p.get("theme") === "light") document.documentElement.classList.remove("dark");
if (p.get("role") === "user") setRole(false);
go(p.get("view") || "home");
