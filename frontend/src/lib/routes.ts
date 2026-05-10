const KNOWN_ROUTE_SEGMENTS = new Set(["login", "register", "chat"]);

function normalizeSegments(pathname: string) {
  return pathname.split("/").filter(Boolean);
}

function normalizeBasePath(basePath: string | undefined) {
  if (!basePath) {
    return "";
  }

  const trimmed = basePath.trim();
  if (!trimmed || trimmed === "/") {
    return "";
  }

  return trimmed.startsWith("/") ? trimmed.replace(/\/+$/, "") : `/${trimmed.replace(/\/+$/, "")}`;
}

function inferBasePath(pathname: string) {
  const segments = normalizeSegments(pathname);
  const firstKnownRouteIndex = segments.findIndex((segment) => KNOWN_ROUTE_SEGMENTS.has(segment));

  if (firstKnownRouteIndex === -1) {
    return segments.length ? `/${segments.join("/")}` : "";
  }

  return firstKnownRouteIndex > 0 ? `/${segments.slice(0, firstKnownRouteIndex).join("/")}` : "";
}

export function getAppBasePath(pathname?: string) {
  const configuredBasePath = normalizeBasePath(process.env.NEXT_PUBLIC_BASE_PATH);
  if (configuredBasePath) {
    return configuredBasePath;
  }

  if (pathname) {
    return inferBasePath(pathname);
  }

  if (typeof window !== "undefined") {
    return inferBasePath(window.location.pathname);
  }

  return "";
}

export function toAppPath(target: string, pathname?: string) {
  const normalizedTarget = target.startsWith("/") ? target : `/${target}`;
  const basePath = getAppBasePath(pathname);

  return `${basePath}${normalizedTarget}` || "/";
}
