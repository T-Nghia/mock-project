const { test, expect } = require("@playwright/test");

const apiUrl = process.env.API_URL?.replace(/\/$/, "");
const smokeEmail = process.env.SMOKE_EMAIL;
const smokePassword = process.env.SMOKE_PASSWORD;

test.beforeAll(() => {
  for (const [name, value] of Object.entries({
    API_URL: apiUrl,
    SMOKE_EMAIL: smokeEmail,
    SMOKE_PASSWORD: smokePassword,
  })) {
    if (!value) throw new Error(`${name} is required`);
  }
});

test("API dependencies are ready", async ({ request }) => {
  const response = await request.get(`${apiUrl}/health/ready`);

  expect(response.status()).toBe(200);
  await expect(response).toBeOK();
  expect(await response.json()).toEqual({ status: "ready" });
});

test("deployed frontend can log in and load the dashboard", async ({ page }) => {
  const apiResponses = [];
  page.on("response", (response) => {
    if (response.url().startsWith(apiUrl)) apiResponses.push(response);
  });

  await page.goto("/login");
  await expect(page.locator("#email")).toBeVisible();

  await page.locator("#email").fill(smokeEmail);
  await page.locator("#password").fill(smokePassword);
  await page.locator('button[type="submit"]').click();

  await expect(page).toHaveURL(/\/dashboard(?:[/?#]|$)/);
  await expect(page.getByText("SLRMS", { exact: true })).toBeVisible();
  await expect(page.locator("h2")).toContainText("Smoke Test");

  expect(
    apiResponses.some(
      (response) => response.url() === `${apiUrl}/auth/me` && response.ok(),
    ),
    "frontend should successfully load the signed-in user from /auth/me",
  ).toBe(true);
  expect(
    apiResponses.some(
      (response) => response.url() === `${apiUrl}/dashboard` && response.ok(),
    ),
    "dashboard API request should succeed",
  ).toBe(true);
});
