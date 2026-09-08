const cjs = "https://" + "cdn.jsdelivr.net" + "/npm/" + "chart.js" + "@4.4.1/+esm";
const sjs = "https://" + "esm.sh" + "/" + "sql.js" + "@1.11.0";
const { Chart } = await import(cjs);
const sqlMod = await import(sjs);
const initSqlJs = sqlMod.default || sqlMod.initSqlJs || sqlMod;
globalThis.Chart = Chart;
globalThis.initSqlJs = initSqlJs;
await import("./app.js");
