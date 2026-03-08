function openErrorWindow(title: string, details: string) {
  void title;
  void details;
}

type ApiOptions = {
  suppressErrorWindow?: boolean;
};

let authTokenProvider: (() => string | null) | null = null;

export function setApiAuthTokenProvider(provider: (() => string | null) | null) {
  authTokenProvider = provider;
}

function authHeaders() {
  const token = authTokenProvider ? authTokenProvider() : null;
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

async function readErrorBody(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return "";
  }
}

export async function apiGet<T>(url: string, options?: ApiOptions): Promise<T> {
  const suppress = Boolean(options?.suppressErrorWindow);
  try {
    const res = await fetch(url, {
      headers: { "Accept": "application/json", ...authHeaders() },
      credentials: "include"
    });
    if (!res.ok) {
      const text = await readErrorBody(res);
      const msg = `${res.status} ${res.statusText}: ${text}`;
      if (!suppress) {
        openErrorWindow("RLCoach API Error", `${url}\n${msg}`);
      }
      throw new Error(msg);
    }
    return (await res.json()) as T;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (!suppress) {
      openErrorWindow("RLCoach Network Error", `${url}\n${msg}`);
    }
    throw err;
  }
}

export async function apiPost<T>(url: string, body: unknown, options?: ApiOptions): Promise<T> {
  const suppress = Boolean(options?.suppressErrorWindow);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json", ...authHeaders() },
      body: JSON.stringify(body ?? {}),
      credentials: "include"
    });
    if (!res.ok) {
      const text = await readErrorBody(res);
      const msg = `${res.status} ${res.statusText}: ${text}`;
      if (!suppress) {
        openErrorWindow("RLCoach API Error", `${url}\n${msg}`);
      }
      throw new Error(msg);
    }
    return (await res.json()) as T;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (!suppress) {
      openErrorWindow("RLCoach Network Error", `${url}\n${msg}`);
    }
    throw err;
  }
}
