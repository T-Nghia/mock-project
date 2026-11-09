const { defineConfig } = require("@playwright/test");
const base = require("./playwright.config");

module.exports = defineConfig(base, {
  testDir: "./security",
  testMatch: "**/security-real-backend.spec.js",
});
