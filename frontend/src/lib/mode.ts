/** True in the static build (`npm run build:static`): the simulation runs in the browser (Pyodide in Web Workers) instead
 * of talking to the local Python server. Model-backed extras (Laya, the Apple on-device model) aren't available there. */
export const STATIC = import.meta.env.VITE_STATIC === '1'
