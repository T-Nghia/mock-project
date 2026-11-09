const { defineConfig } = require("@playwright/test");
const base = require("./playwright.config");

// These contracts use page.route API fixtures. Shared-environment smoke/lifecycle
// tests remain separate; no staging account or external storage is used here.
module.exports = defineConfig(base, {
  testIgnore: ["**/post-deploy.spec.js", "**/document-lifecycle.spec.js"],
  webServer: {
    command: "npm --prefix ../frontend run start",
    url: process.env.APP_URL,
    reuseExistingServer: false,
  },
});
