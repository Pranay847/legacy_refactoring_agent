const API_BASE = "http://localhost:8000/api";

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
    body: formData,
  });

  return parseJsonResponse(response, "Failed to upload files");
}

export async function sendChatMessage(sessionId, message) {
  const response = await fetch(`${API_BASE}/chat/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
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
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ repo_path: repoPath }),
  });

  return parseJsonResponse(response, "Failed to scan repository");
}

export async function calculateMicroservices() {
  const response = await fetch(`${API_BASE}/cluster`, {
    method: "POST",
  });

  return parseJsonResponse(response, "Failed to calculate microservices");
}

export async function fetchGraph() {
  const response = await fetch(`${API_BASE}/graph`);
  return parseJsonResponse(response, "Failed to load graph");
}

export async function generateMicroservice(clusterName, repoPath) {
  const response = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      cluster_name: clusterName,
      repo_path: repoPath,
    }),
  });

  return parseJsonResponse(response, "Failed to generate microservice");
}

export async function fetchServiceFile(serviceName, fileName) {
  const response = await fetch(
    `${API_BASE}/services/${encodeURIComponent(serviceName)}/${encodeURIComponent(fileName)}`
  );

  return parseJsonResponse(response, "Failed to load generated file");
}

export async function resetWorkspace() {
  const response = await fetch(`${API_BASE}/reset`, {
    method: "POST",
  });

  return parseJsonResponse(response, "Failed to reset workspace");
}

export async function listServices() {
  const response = await fetch(`${API_BASE}/services`);
  return parseJsonResponse(response, "Failed to list services");
}
