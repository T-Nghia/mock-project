const { test, expect } = require("@playwright/test");

test("disabled image optimizer rejects benign requests without affecting static assets", async ({ request }) => {
  for (const path of ["/_next/image", "/_next/image?url=%2Ffavicon.ico&w=64&q=75"]) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(404);
  }
  const login = await request.get("/login");
  expect(login.status()).toBe(200);
  const html = await login.text();
  const assets = [...html.matchAll(/(?:src|href)="([^" ]*\/_next\/static\/[^" ]+)"/g)]
    .map((match) => match[1].replaceAll("&amp;", "&"));
  expect(assets.length).toBeGreaterThan(0);
  for (const asset of new Set(assets)) {
    expect((await request.get(asset)).status(), asset).toBe(200);
  }
});
