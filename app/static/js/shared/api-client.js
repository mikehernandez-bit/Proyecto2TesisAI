export async function requestJson(url, { method = "GET", body } = {}) {
  const options = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }
  if (!response.ok) {
    const detail = payload?.detail;
    if (Array.isArray(detail)) {
      throw new Error(detail.map((item) => item?.msg || JSON.stringify(item)).join("; "));
    }
    throw new Error(typeof detail === "string" ? detail : `HTTP ${response.status}`);
  }
  return payload;
}
