export async function getJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
    },
    ...options,
  });

  if (!response.ok) {
    throw await buildError(response);
  }

  return response.json();
}

export async function postJson(url, payload, options = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    ...options,
  });

  if (!response.ok) {
    throw await buildError(response);
  }

  return response.json();
}

export async function postForm(url, formData, options = {}) {
  const response = await fetch(url, {
    method: "POST",
    body: formData,
    ...options,
  });

  if (!response.ok) {
    throw await buildError(response);
  }

  return response.json();
}

export function postFormWithProgress(url, formData, options = {}) {
  const { onProgress, timeoutMs, headers = {} } = options;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.responseType = "text";

    if (typeof timeoutMs === "number" && Number.isFinite(timeoutMs) && timeoutMs > 0) {
      xhr.timeout = timeoutMs;
    }

    for (const [key, value] of Object.entries(headers)) {
      if (value !== undefined && value !== null) {
        xhr.setRequestHeader(key, String(value));
      }
    }

    xhr.upload.addEventListener("progress", (event) => {
      if (typeof onProgress === "function") {
        onProgress(event);
      }
    });

    xhr.addEventListener("load", async () => {
      const response = buildXhrResponse(xhr);
      if (!response.ok) {
        reject(await buildError(response));
        return;
      }
      try {
        resolve(await response.json());
      } catch (_error) {
        reject(new Error("Server returned invalid JSON."));
      }
    });

    xhr.addEventListener("error", () => reject(new Error("Network request failed.")));
    xhr.addEventListener("timeout", () => reject(new Error("Upload request timed out.")));
    xhr.addEventListener("abort", () => reject(new Error("Upload request was aborted.")));
    xhr.send(formData);
  });
}

async function buildError(response) {
  let detail = response.statusText;
  try {
    const payload = await response.json();
    detail = payload.detail || JSON.stringify(payload);
  } catch (_error) {
    detail = response.statusText;
  }
  return new Error(detail);
}

function buildXhrResponse(xhr) {
  const contentType = xhr.getResponseHeader("Content-Type") || "";
  const responseText = xhr.responseText || "";
  return {
    ok: xhr.status >= 200 && xhr.status < 300,
    status: xhr.status,
    statusText: xhr.statusText || "Request failed",
    async json() {
      if (!responseText) {
        return {};
      }
      if (contentType.toLowerCase().includes("application/json")) {
        return JSON.parse(responseText);
      }
      return JSON.parse(responseText);
    },
  };
}
