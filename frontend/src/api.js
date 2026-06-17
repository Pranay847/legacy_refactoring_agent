const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

// Auth token injection: a component inside ClerkProvider registers a getter so
// these plain (non-React) functions can attach the bearer token. When auth is
// disabled or the user is signed out, no header is added and requests go through
// unauthenticated (the backend treats that as the local-dev principal).
let authTokenGetter = null;

export function setAuthTokenGetter(getter) {
  authTokenGetter = getter;
}

async function authHeaders(base = {}) {
  const headers = { ...base };
  if (authTokenGetter) {
    try {
      const token = await authTokenGetter();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    } catch {
      // No token available — fall through and send the request unauthenticated.
    }
  }
  return headers;
}

async function parseJsonResponse(response, fallbackMessage) {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.detail || data?.message || fallbackMessage);
  }

  return data;
}

export async function uploadSessionFiles(sessionId, files, projectName) {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  if (projectName) {
    formData.append("project_name", projectName);
  }

  files.forEach((file) => {
    formData.append("files", file, file.webkitRelativePath || file.name);
  });

  const response = await fetch(`${API_BASE}/ingest/`, {
    method: "POST",
    // No Content-Type: the browser sets the multipart boundary itself.
    headers: await authHeaders(),
    body: formData,
  });

  return parseJsonResponse(response, "Failed to upload files");
}

export async function sendChatMessage(sessionId, message) {
  const response = await fetch(`${API_BASE}/chat/`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      session_id: sessionId,
      message,
    }),
  });

  return parseJsonResponse(response, "Failed to send message");
}

export async function scanRepository(repoPath) {
  const response = await fetch(`${API_BASE}/scan`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ repo_path: repoPath }),
  });

  return parseJsonResponse(response, "Failed to scan repository");
}

export async function calculateMicroservices() {
  const response = await fetch(`${API_BASE}/cluster`, {
    method: "POST",
    headers: await authHeaders(),
  });

  return parseJsonResponse(response, "Failed to calculate microservices");
}

export async function fetchGraph() {
  const response = await fetch(`${API_BASE}/graph`, {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Failed to load graph");
}

export async function generateMicroservice(clusterName, repoPath) {
  const response = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      cluster_name: clusterName,
      repo_path: repoPath,
    }),
  });

  return parseJsonResponse(response, "Failed to generate microservice");
}

export async function generateAllMicroservices(clusterNames, repoPath) {
  const response = await fetch(`${API_BASE}/generate-all`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      cluster_names: clusterNames,
      repo_path: repoPath,
    }),
  });

  return parseJsonResponse(response, "Failed to generate microservices");
}

export async function enqueueGenerateAllAsync(clusterNames, repoPath) {
  const response = await fetch(`${API_BASE}/generate-all/async`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      cluster_names: clusterNames,
      repo_path: repoPath,
    }),
  });

  return parseJsonResponse(response, "Failed to queue generation");
}

export async function fetchJob(jobId) {
  const response = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}`, {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Failed to fetch job status");
}

export async function fetchServiceFile(serviceName, fileName) {
  const response = await fetch(
    `${API_BASE}/services/${encodeURIComponent(serviceName)}/${encodeURIComponent(fileName)}`,
    { headers: await authHeaders() }
  );

  return parseJsonResponse(response, "Failed to load generated file");
}

export async function resetWorkspace() {
  const response = await fetch(`${API_BASE}/reset`, {
    method: "POST",
    headers: await authHeaders(),
  });

  return parseJsonResponse(response, "Failed to reset workspace");
}

export async function listServices() {
  const response = await fetch(`${API_BASE}/services`, {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Failed to list services");
}

export async function fetchStatus() {
  const response = await fetch(`${API_BASE}/status`, {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Failed to load status");
}

// ---------------------------------------------------------------------------
// Billing (gated). These are safe to call even when billing is disabled: the
// backend returns a free-plan shape for the subscription and 503 for checkout.
// ---------------------------------------------------------------------------
export async function fetchSubscription() {
  const response = await fetch(`${API_BASE}/billing/subscription`, {
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Failed to load subscription");
}

export async function startCheckout(plan) {
  const response = await fetch(`${API_BASE}/billing/checkout`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ plan }),
  });
  return parseJsonResponse(response, "Failed to start checkout");
}

export async function openBillingPortal() {
  const response = await fetch(`${API_BASE}/billing/portal`, {
    method: "POST",
    headers: await authHeaders(),
  });
  return parseJsonResponse(response, "Failed to open billing portal");
}
