function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
}
function fmtRelative(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = /* @__PURE__ */ new Date();
  const sec = Math.floor((now.getTime() - d.getTime()) / 1e3);
  if (sec < 60) return `il y a ${sec}s`;
  if (sec < 3600) return `il y a ${Math.floor(sec / 60)} min`;
  if (sec < 86400) return `il y a ${Math.floor(sec / 3600)} h`;
  if (sec < 86400 * 30) return `il y a ${Math.floor(sec / 86400)} j`;
  return fmtDate(iso);
}
function fmtNum(n) {
  if (n == null) return "—";
  return n.toLocaleString("fr-FR");
}
function truncate(s, n = 180) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}
export {
  fmtNum as a,
  fmtDate as b,
  fmtRelative as f,
  truncate as t
};
