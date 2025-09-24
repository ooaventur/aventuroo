const HEALTH_PATH = "/_health/autopost.json";
const DEFAULT_MIN_ITEMS = 1;
const DEFAULT_MAX_AGE_MINUTES = 120;
const MAX_ERROR_LINES = 3;

const NO_CACHE_HEADERS = {
  "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
  "CDN-Cache-Control": "no-store",
  "Surrogate-Control": "no-store",
  Pragma: "no-cache"
};

function parseInteger(value, fallback) {
  if (value === undefined || value === null) {
    return fallback;
  }
  const parsed = parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function buildAlert(env, alertName, summary, description, severityOverride) {
  const now = new Date().toISOString();
  const severity = severityOverride || env.ALERTMANAGER_SEVERITY || "critical";
  const service = env.ALERTMANAGER_SERVICE || "aventuroo-autopost";
  return {
    labels: {
      alertname: alertName,
      service,
      severity
    },
    annotations: {
      summary,
      description
    },
    startsAt: now
  };
}

async function sendAlerts(alerts, env) {
  if (!alerts.length || !env.ALERTMANAGER_WEBHOOK) {
    return;
  }

  try {
    await fetch(env.ALERTMANAGER_WEBHOOK, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(alerts)
    });
  } catch (error) {
    console.error("Failed to send alerts to Alertmanager", error);
  }
}

function withNoCacheHeaders(response) {
  const forwarded = new Response(response.body, response);
  for (const [key, value] of Object.entries(NO_CACHE_HEADERS)) {
    forwarded.headers.set(key, value);
  }
  return forwarded;
}

function resolveOriginUrl(requestUrl, env) {
  if (!env.HEALTH_ORIGIN) {
    return new URL(requestUrl);
  }
  const origin = new URL(env.HEALTH_ORIGIN);
  const url = new URL(requestUrl);
  url.protocol = origin.protocol;
  url.hostname = origin.hostname;
  url.port = origin.port;
  return url;
}

async function fetchFromOrigin(request, env) {
  const originUrl = resolveOriginUrl(request.url, env);
  const init = {
    method: request.method,
    headers: new Headers(request.headers)
  };

  if (env.HEALTH_ORIGIN) {
    const hostHeader = originUrl.host || originUrl.hostname;
    init.headers.set("host", hostHeader);
  }

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  const originRequest = new Request(originUrl.toString(), init);
  return fetch(originRequest, {
    cf: {
      cacheTtl: 0,
      cacheEverything: false,
      cacheKey: undefined
    }
  });
}

function evaluateMetrics(data, env) {
  const alerts = [];
  const now = new Date();
  const minItems = parseInteger(
    env.MIN_ITEMS_INGESTED ?? env.MIN_ITEMS_PUBLISHED,
    DEFAULT_MIN_ITEMS
  );
  const maxAgeMinutes = parseInteger(env.MAX_HEALTH_AGE_MINUTES, DEFAULT_MAX_AGE_MINUTES);

  const itemsRaw = data.items_ingested ?? data.items_published;
  const items = Number(itemsRaw);
  if (!Number.isFinite(items) || items < minItems) {
    alerts.push(
      buildAlert(
        env,
        "AutopostLowPublication",
        `Autopost ingested ${items} items`,
        `Minimum expected items is ${minItems}, received ${items}`,
        env.ALERTMANAGER_SEVERITY_LOW || env.ALERTMANAGER_SEVERITY || "critical"
      )
    );
  }

  const lastFetchRaw = data.last_fetch ?? data.last_run;
  const lastFetch = lastFetchRaw ? new Date(lastFetchRaw) : null;
  if (!lastFetch || Number.isNaN(lastFetch.getTime())) {
    alerts.push(
      buildAlert(
        env,
        "AutopostMissingTimestamp",
        "Autopost last_fetch timestamp missing",
        `Payload contained last_fetch=${JSON.stringify(lastFetchRaw)}`
      )
    );
  } else {
    const diffMinutes = Math.abs(now.getTime() - lastFetch.getTime()) / 60000;
    if (diffMinutes > maxAgeMinutes) {
      alerts.push(
        buildAlert(
          env,
          "AutopostStale",
          `Autopost last fetched ${Math.round(diffMinutes)} minutes ago`,
          `Maximum allowed freshness is ${maxAgeMinutes} minutes`
        )
      );
    }
  }

  const errors = Array.isArray(data.errors) ? data.errors.filter(Boolean) : [];
  if (errors.length) {
    const displayed = errors.slice(0, MAX_ERROR_LINES).join("\n");
    const extra = errors.length > MAX_ERROR_LINES ? ` (and ${errors.length - MAX_ERROR_LINES} more)` : "";
    alerts.push(
      buildAlert(
        env,
        "AutopostErrors",
        "Autopost run reported errors",
        `${displayed}${extra}`,
        env.ALERTMANAGER_SEVERITY || "critical"
      )
    );
  }

  return alerts;
}

async function processHealthResponse(response, env) {
  const alerts = [];

  if (!response) {
    alerts.push(
      buildAlert(env, "AutopostHealthUnavailable", "Autopost health unavailable", "No response from origin")
    );
    await sendAlerts(alerts, env);
    return alerts;
  }

  if (!response.ok) {
    const description = `Origin responded with status ${response.status}`;
    alerts.push(buildAlert(env, "AutopostHealthHttpError", "Autopost health request failed", description));
    await sendAlerts(alerts, env);
    return alerts;
  }

  let payload;
  try {
    payload = await response.json();
  } catch (error) {
    alerts.push(
      buildAlert(env, "AutopostHealthParseError", "Failed to parse autopost health payload", String(error))
    );
    await sendAlerts(alerts, env);
    return alerts;
  }

  const metricAlerts = evaluateMetrics(payload, env);
  alerts.push(...metricAlerts);
  await sendAlerts(alerts, env);
  return alerts;
}

async function runScheduledHealthCheck(env) {
  if (!env.HEALTH_ORIGIN) {
    console.warn("HEALTH_ORIGIN not configured; skipping scheduled health check");
    return;
  }

  try {
    const base = new URL(env.HEALTH_ORIGIN);
    base.pathname = HEALTH_PATH;
    const response = await fetch(base.toString(), {
      headers: { Accept: "application/json" },
      cf: { cacheTtl: 0, cacheEverything: false }
    });
    await processHealthResponse(response, env);
  } catch (error) {
    const alert = buildAlert(
      env,
      "AutopostHealthFetchError",
      "Scheduled health check failed",
      String(error)
    );
    await sendAlerts([alert], env);
    console.error("Scheduled autopost health check failed", error);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === HEALTH_PATH) {
      const originResponse = await fetchFromOrigin(request, env);
      const cloned = originResponse.clone();
      ctx.waitUntil(processHealthResponse(cloned, env));
      return withNoCacheHeaders(originResponse);
    }

    return fetch(request);
  },

  async scheduled(event, env, ctx) {
    ctx.waitUntil(runScheduledHealthCheck(env));
  }
};
