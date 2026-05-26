

export const index = 0;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/_layout.svelte.js')).default;
export const universal = {
  "prerender": false,
  "ssr": false,
  "csr": true
};
export const universal_id = "src/routes/+layout.ts";
export const imports = ["_app/immutable/nodes/0.DtjRLX-F.js","_app/immutable/chunks/gycu33U8.js","_app/immutable/chunks/DtJaO0-0.js","_app/immutable/chunks/w0biL3VK.js","_app/immutable/chunks/27MhRw_W.js","_app/immutable/chunks/DxZn4tcf.js","_app/immutable/chunks/CKtC6-w_.js"];
export const stylesheets = ["_app/immutable/assets/0.DEh3LGS4.css"];
export const fonts = [];
