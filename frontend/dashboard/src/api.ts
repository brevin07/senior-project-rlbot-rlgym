function openErrorWindow(title: string, details: string) {
  try {
    const win = window.open("", "rlcoach_errors", "width=620,height=600");
    if (!win) {
      return;
    }
    const safe = details.replace(/</g, "&lt;").replace(/>/g, "&gt;");
    win.document.title = title;
    win.document.body.style.fontFamily = "monospace";
    win.document.body.style.whiteSpace = "pre-wrap";
    win.document.body.style.padding = "16px";
    win.document.body.innerHTML = `<h3>${title}</h3><pre>${safe}</pre>`;
  } catch {
    // ignore
  }
}

async function readErrorBody(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return "";
  }
}

export async function apiGet<T>(url: string): Promise<T> {
  try {
    const res = await fetch(url, {
      headers: { "Accept": "application/json" },
      credentials: "include"
    });
    if (!res.ok) {
      const text = await readErrorBody(res);
      const msg = `${res.status} ${res.statusText}: ${text}`;
      openErrorWindow("RLCoach API Error", `${url}\n${msg}`);
      throw new Error(msg);
    }
    return (await res.json()) as T;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    openErrorWindow("RLCoach Network Error", `${url}\n${msg}`);
    throw err;
  }
}

export async function apiPost<T>(url: string, body: unknown): Promise<T> {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body ?? {}),
      credentials: "include"
    });
    if (!res.ok) {
      const text = await readErrorBody(res);
      const msg = `${res.status} ${res.statusText}: ${text}`;
      openErrorWindow("RLCoach API Error", `${url}\n${msg}`);
      throw new Error(msg);
    }
    return (await res.json()) as T;
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    openErrorWindow("RLCoach Network Error", `${url}\n${msg}`);
    throw err;
  }
}
