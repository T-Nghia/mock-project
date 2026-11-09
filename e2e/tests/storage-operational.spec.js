const { test, expect } = require("@playwright/test");
const crypto = require("node:crypto");

test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });
test.beforeAll(() => {
  if (process.env.RUN_OPERATIONAL_E2E !== "1") throw new Error("Run via the disposable operational acceptance runner");
  for (const name of ["API_URL", "M3_CLOSED_API_URL", "SMOKE_EMAIL", "SMOKE_PASSWORD"]) {
    if (!process.env[name]) throw new Error(`${name} is required`);
  }
  for (const address of [process.env.API_URL, process.env.M3_CLOSED_API_URL, process.env.APP_URL]) {
    if (!["localhost", "127.0.0.1"].includes(new URL(address).hostname)) throw new Error("Loopback test targets required");
  }
});

async function login(request, email = process.env.SMOKE_EMAIL) {
  const response = await request.post(`${process.env.API_URL}/auth/login`, {
    data: { email, password: process.env.SMOKE_PASSWORD },
  });
  expect(response.status()).toBe(200);
  return { Authorization: `Bearer ${(await response.json()).access_token}` };
}

async function upload(request, headers) {
  const marker = `M3-${crypto.randomUUID()}`;
  const response = await request.post(`${process.env.API_URL}/documents/upload`, {
    headers, multipart: { title: marker, file: { name: `${marker}.txt`, mimeType: "text/plain", buffer: Buffer.from(`${marker}\nRetained evidence for the deletion acceptance test.\n`) } },
  });
  expect(response.status()).toBe(201);
  const document = await response.json();
  await expect.poll(async () => {
    const result = await request.get(`${process.env.API_URL}/documents/${document.id}`, { headers });
    expect(result.status()).toBe(200);
    return (await result.json()).processing_status;
  }).toBe("done");
  return document;
}

test("real backend retains private read-only chat and citation UI after document cleanup", async ({ page }) => {
  const headers = await login(page.request);
  const document = await upload(page.request, headers);
  const created = await page.request.post(`${process.env.API_URL}/chat/sessions`, { headers, data: { document_id: document.id } });
  expect(created.status()).toBe(201);
  const session = await created.json();
  const answer = await page.request.post(`${process.env.API_URL}/chat/sessions/${session.id}/messages`, { headers, data: { content: "What evidence is retained?" } });
  expect(answer.status()).toBe(201);
  expect((await answer.json()).sources.length).toBeGreaterThan(0);
  const before = await page.request.get(`${process.env.API_URL}/chat/sessions/${session.id}`, { headers });
  const messages = (await before.json()).messages;
  expect((await page.request.delete(`${process.env.API_URL}/documents/${document.id}`, { headers })).status()).toBe(204);
  expect((await page.request.delete(`${process.env.API_URL}/documents/${document.id}`, { headers })).status()).toBe(404);
  const after = await page.request.get(`${process.env.API_URL}/chat/sessions/${session.id}`, { headers });
  const orphan = await after.json();
  expect(orphan.document_id).toBeNull();
  expect(orphan.messages).toEqual(messages);
  expect((await page.request.post(`${process.env.API_URL}/chat/sessions/${session.id}/messages`, { headers, data: { content: "Cannot write" } })).status()).toBe(409);

  // Browser performs real refresh/me/session requests; no route interception.
  await page.goto(`/chat/${session.id}`);
  await expect(page.getByRole("status")).toContainText("Cuộc trò chuyện này chỉ đọc");
  await expect(page.getByText("Local acceptance answer with retained evidence.", { exact: true })).toBeVisible();
  await expect(page.locator("textarea")).toHaveCount(0);
  await page.getByText(/^\[1\]/).first().click();
  await expect(page.getByText(/Retained evidence for the deletion acceptance test/).last()).toBeVisible();

  const other = await login(page.request, "m3-other@example.com");
  expect((await page.request.get(`${process.env.API_URL}/chat/sessions/${session.id}`, { headers: other })).status()).toBe(404);
  expect((await page.request.delete(`${process.env.API_URL}/chat/sessions/${session.id}`, { headers: other })).status()).toBe(404);
  expect((await page.request.delete(`${process.env.API_URL}/chat/sessions/${session.id}`, { headers })).status()).toBe(204);
});

test("closed real backend gates reject document mutations while reads remain available", async ({ page }) => {
  const headers = await login(page.request);
  const document = await upload(page.request, headers);
  const address = `${process.env.M3_CLOSED_API_URL}/documents/${document.id}`;
  const refused = await page.request.delete(address, { headers });
  expect(refused.status()).toBe(503);
  expect(refused.headers()["retry-after"]).toBeTruthy();
  expect((await page.request.get(address, { headers })).status()).toBe(200);
  const download = await page.request.get(`${address}/download`, { headers });
  expect(download.status()).toBe(200);
  expect((await download.body()).length).toBeGreaterThan(0);
  expect((await page.request.post(`${process.env.M3_CLOSED_API_URL}/documents/upload`, { headers, multipart: { file: { name: "refused.txt", mimeType: "text/plain", buffer: Buffer.from("refused") } } })).status()).toBe(503);
  const concurrent = await Promise.all([
    page.request.delete(`${process.env.API_URL}/documents/${document.id}`, { headers }),
    page.request.delete(`${process.env.API_URL}/documents/${document.id}`, { headers }),
  ]);
  expect(concurrent.map((response) => response.status()).sort()).toEqual([204, 404]);
});
