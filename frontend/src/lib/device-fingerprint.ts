/**
 * Privacy-preserving device fingerprint.
 *
 * Hanya hash yang dikirim ke backend. Seed acak disimpan di localStorage agar
 * perangkat yang sama tetap stabil walau beberapa sinyal browser berubah.
 */
const STORAGE_KEY = "clipzi_device_seed";
let cached: Promise<string> | null = null;

function fallbackHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

async function sha256(value: string): Promise<string> {
  if (typeof crypto !== "undefined" && crypto.subtle) {
    const bytes = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  }
  return fallbackHash(value);
}

function persistentSeed(): string {
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;
    const generated =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random()}`;
    window.localStorage.setItem(STORAGE_KEY, generated);
    return generated;
  } catch {
    return "no-storage";
  }
}

function canvasSignature(): string {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 220;
    canvas.height = 40;
    const context = canvas.getContext("2d");
    if (!context) return "no-canvas";
    context.textBaseline = "top";
    context.font = "14px Arial";
    context.fillStyle = "#f60";
    context.fillRect(0, 0, 220, 40);
    context.fillStyle = "#069";
    context.fillText("Clipzi device check", 4, 8);
    return canvas.toDataURL().slice(-120);
  } catch {
    return "canvas-error";
  }
}

function webglSignature(): string {
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl") ||
      (canvas.getContext("experimental-webgl") as WebGLRenderingContext | null);
    if (!gl) return "no-webgl";
    const debug = gl.getExtension("WEBGL_debug_renderer_info");
    return [
      gl.getParameter(gl.VENDOR),
      gl.getParameter(gl.RENDERER),
      debug ? gl.getParameter(debug.UNMASKED_VENDOR_WEBGL) : "",
      debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : "",
    ].join("|");
  } catch {
    return "webgl-error";
  }
}

export async function getDeviceFingerprint(): Promise<string> {
  if (cached) return cached;
  cached = (async () => {
    const nav = navigator as Navigator & { deviceMemory?: number };
    const parts = [
      persistentSeed(),
      nav.userAgent,
      nav.language,
      (nav.languages || []).join(","),
      nav.platform,
      Intl.DateTimeFormat().resolvedOptions().timeZone,
      String(nav.hardwareConcurrency || 0),
      String(nav.deviceMemory || 0),
      `${screen.width}x${screen.height}x${screen.colorDepth}`,
      canvasSignature(),
      webglSignature(),
    ];
    return sha256(parts.join("|"));
  })();
  return cached;
}

export async function deviceFingerprintHeader(): Promise<{ "X-Device-Fingerprint": string }> {
  return { "X-Device-Fingerprint": await getDeviceFingerprint() };
}
