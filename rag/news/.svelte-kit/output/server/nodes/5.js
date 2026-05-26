

export const index = 5;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/stats/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/5.CH2v5LWe.js","_app/immutable/chunks/gycu33U8.js","_app/immutable/chunks/DtJaO0-0.js","_app/immutable/chunks/w0biL3VK.js","_app/immutable/chunks/ChofwjQv.js"];
export const stylesheets = [];
export const fonts = [];
