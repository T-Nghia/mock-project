const { test, expect } = require("@playwright/test");
const crypto = require("node:crypto");

const apiUrl = process.env.API_URL?.replace(/\/$/, "");
const email = process.env.SMOKE_EMAIL;
const password = process.env.SMOKE_PASSWORD;
const processingTimeout = Number(process.env.DOCUMENT_PROCESSING_TIMEOUT_MS || 180_000);

async function login(request) {
  const response = await request.post(`${apiUrl}/auth/login`, {
    data: { email, password },
  });
  expect(response.status(), await response.text()).toBe(200);
  const body = await response.json();
  expect(body.access_token).toBeTruthy();
  return body.access_token;
}

async function waitForProcessing(request, headers, documentId) {
  const deadline = Date.now() + processingTimeout;
  let lastMetadata;
  while (Date.now() < deadline) {
    const response = await request.get(`${apiUrl}/documents/${documentId}`, { headers });
    expect(response.status(), await response.text()).toBe(200);
    lastMetadata = await response.json();
    if (lastMetadata.processing_status === "done") return lastMetadata;
    if (lastMetadata.processing_status === "failed") {
      throw new Error(`Document processing failed: ${lastMetadata.processing_last_error || "unknown"}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
  throw new Error(
    `Document ${documentId} did not finish within ${processingTimeout}ms; last state: ${JSON.stringify(lastMetadata)}`,
  );
}

test.beforeAll(() => {
  for (const [name, value] of Object.entries({
    API_URL: apiUrl,
    SMOKE_EMAIL: email,
    SMOKE_PASSWORD: password,
  })) {
    if (!value) throw new Error(`${name} is required`);
  }
});

test("upload, process, search, chat, download, and delete a document", async ({ request }) => {
  const marker = `SLRMS-E2E-${crypto.randomUUID()}`;
  const content = Buffer.from(`${marker}\nThis document verifies the complete staging lifecycle.\n`, "utf8");
  const token = await login(request);
  const headers = { Authorization: `Bearer ${token}` };
  let documentId;
  let sessionId;

  try {
    const upload = await request.post(`${apiUrl}/documents/upload`, {
      headers,
      multipart: {
        file: { name: `${marker}.txt`, mimeType: "text/plain", buffer: content },
        title: marker,
        tags: "e2e,lifecycle",
      },
    });
    expect(upload.status(), await upload.text()).toBe(201);
    const uploaded = await upload.json();
    documentId = uploaded.id;
    expect(["pending", "processing"]).toContain(uploaded.processing_status);

    const metadata = await waitForProcessing(request, headers, documentId);
    expect(metadata.title).toBe(marker);
    expect(metadata.processing_attempts).toBeGreaterThanOrEqual(1);
    expect(metadata.processing_last_error).toBeNull();

    const search = await request.get(`${apiUrl}/search`, {
      headers,
      params: { keyword: marker, page: 1, page_size: 20 },
    });
    expect(search.status(), await search.text()).toBe(200);
    expect((await search.json()).items.some((item) => item.id === documentId)).toBeTruthy();

    const createSession = await request.post(`${apiUrl}/chat/sessions`, {
      headers,
      data: { document_id: documentId },
    });
    expect(createSession.status(), await createSession.text()).toBe(201);
    sessionId = (await createSession.json()).id;

    const answer = await request.post(`${apiUrl}/chat/sessions/${sessionId}/messages`, {
      headers,
      data: { content: `What unique marker appears in this document?` },
    });
    expect(answer.status(), await answer.text()).toBe(201);
    const answerBody = await answer.json();
    expect(answerBody.answer).toBeTruthy();
    expect(answerBody.sources.length).toBeGreaterThan(0);

    const download = await request.get(`${apiUrl}/documents/${documentId}/download`, { headers });
    expect(download.status(), await download.text()).toBe(200);
    expect(Buffer.compare(await download.body(), content)).toBe(0);
  } finally {
    if (sessionId) {
      await request.delete(`${apiUrl}/chat/sessions/${sessionId}`, { headers });
    }
    if (documentId) {
      const deletion = await request.delete(`${apiUrl}/documents/${documentId}`, { headers });
      expect([204, 404]).toContain(deletion.status());
      const missing = await request.get(`${apiUrl}/documents/${documentId}`, { headers });
      expect(missing.status()).toBe(404);
    }
  }
});
