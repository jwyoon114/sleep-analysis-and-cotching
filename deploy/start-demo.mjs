import {existsSync} from "node:fs";
import {resolve, dirname} from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";

export function demoEnvironment(current) {
  if (current.DALJAM_DEMO_ONLY !== "1") throw new Error("DALJAM_DEMO_ONLY must be 1.");
  const port = current.PORT ?? "10000";
  if (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
    throw new Error("PORT must be an integer from 1 to 65535.");
  }
  const env = Object.fromEntries(Object.entries(current).filter(([name]) =>
    !name.startsWith("PG") && !name.startsWith("OPENAI_") &&
    !["DATABASE_URL", "SLEEP_DB_PATH", "SLEEP_DB_BACKEND", "SLEEP_API_URL"].includes(name)));
  return {...env, PORT:String(Number(port)), HOSTNAME:"0.0.0.0", NODE_ENV:"production",
    NEXT_TELEMETRY_DISABLED:"1", COACHING_ENGINE:"rules"};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const env = demoEnvironment(process.env);
    const server = resolve(process.argv[2] || resolve(dirname(fileURLToPath(import.meta.url)), "../web/server.js"));
    if (!existsSync(server)) throw new Error("Build the standalone web server first.");
    for (const name of Object.keys(process.env)) if (!(name in env)) delete process.env[name];
    Object.assign(process.env, env);
    // Run in one process. Next.js owns HTTP and graceful shutdown handlers.
    await import(pathToFileURL(server).href);
  } catch {
    console.error("Demo startup failed. Check demo mode, PORT and standalone build.");
    process.exitCode = 1;
  }
}
