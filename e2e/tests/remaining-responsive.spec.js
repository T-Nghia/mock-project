const { test, expect, ids, fits } = require("./remaining-pages-fixture");
test.use({ channel: process.env.UI_BROWSER_CHANNEL || undefined, video: "off" });
const pages = [
  { slug: "folders", path: "/folders", heading: "Thư mục của bạn", role: "teacher" },
  { slug: "bookmarks", path: "/bookmarks", heading: "Tài liệu đã lưu", role: "student" },
  { slug: "admin-users", path: "/admin/users", heading: "Quản lý người dùng", role: "admin" },
  { slug: "login", path: "/login", heading: "Đăng nhập SLRMS", public: true },
  { slug: "register", path: "/register", heading: "Tạo tài khoản học sinh", public: true },
  { slug: "forgot-password", path: "/forgot-password", heading: "Quên mật khẩu", public: true },
  { slug: "reset-password", path: "/reset-password?token=screenshot-token", heading: "Đặt lại mật khẩu", public: true },
];
async function ready(page, config) {
  await expect(page.getByRole("main").getByRole("heading", { name: config.heading, exact: true })).toBeVisible();
  if (!config.public) await expect(page.getByRole("main").getByRole("status", { name: /^Đang tải/ })).toHaveCount(0);
}
for (const config of pages) {
  for (const width of [320, 390, 768, 1024, 1440]) test(config.slug + " fits and supports keyboard at " + width, async ({ page, mock }) => {
    const state = await mock(config); await page.setViewportSize({ width, height: 1000 });
    state.bookmarks[0].title = "TaiLieuNghienCuu".repeat(30);
    state.users[0].full_name = "NguoiDung".repeat(24);
    state.users[0].email = "longaccount".repeat(15) + "@example.com";
    state.folders[1].name = "ThuMucLong".repeat(20);
    let parent = ids.child;
    for (let i = 3; i < 10; i++) { const id = `10000000-0000-4000-8000-${String(i).padStart(12, "0")}`; state.folders.push({ ...state.folders[0], id, parent_folder_id: parent, name: `Cấp ${i}` }); parent = id; }
    await page.goto(config.path); await ready(page, config); await fits(page);
    if (config.public) {
      const field = page.getByRole("main").locator("input").first(); await field.focus(); await expect(field).toBeFocused();
      const inputs = page.getByRole("main").locator("input"); for (const input of await inputs.all()) await expect(input).toHaveAccessibleName(/.+/);
    } else if (config.slug === "folders") {
      await page.getByRole("button", { name: "Thao tác với thư mục " + state.folders[1].name, exact: true }).click();
      await page.getByRole("menuitem", { name: "Thư mục con", exact: true }).click(); await fits(page);
      const dialog = page.getByRole("dialog"); expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
      await page.keyboard.press("Escape");
    } else if (config.slug === "admin-users") {
      await page.getByRole("button", { name: "Thêm giáo viên" }).click(); const dialog = page.getByRole("dialog");
      expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true); await page.keyboard.press("Escape");
    } else { const link = page.getByRole("main").getByRole("link", { name: state.bookmarks[0].title, exact: true }); await link.focus(); await expect(link).toBeFocused(); }
    await fits(page);
  });
  test("captures " + config.slug + " desktop and mobile", async ({ page, mock }) => {
    await mock(config); await page.setViewportSize({ width: 1440, height: 1100 }); await page.goto(config.path); await ready(page, config);
    if (config.slug === "folders") { await page.getByRole("button", { name: "Nghiên cứu AI", exact: true }).click(); await expect(page.getByLabel("Chuyển tài liệu tới", { exact: true })).toBeVisible(); }
    await page.screenshot({ path: test.info().outputPath(config.slug + "-desktop.png"), animations: "disabled" });
    await page.setViewportSize({ width: 390, height: 1000 }); await page.screenshot({ path: test.info().outputPath(config.slug + "-mobile.png"), animations: "disabled" });
  });
}

test("reduced motion applies to loading and modal animations", async ({ page, mock }) => {
  const state = await mock(); const release = state.pause("GET /folders/tree"); await page.emulateMedia({ reducedMotion: "reduce" }); await page.goto("/folders");
  await expect(page.getByRole("status", { name: "Đang tải thư mục" })).toBeVisible();
  expect(await page.locator(".animate-pulse").first().evaluate((el) => parseFloat(getComputedStyle(el).animationDuration))).toBeLessThanOrEqual(0.001);
  release(); await page.getByRole("button", { name: "Tạo thư mục", exact: true }).click();
  expect(await page.getByRole("dialog").locator(".animate-slide-up").evaluate((el) => parseFloat(getComputedStyle(el).animationDuration))).toBeLessThanOrEqual(0.001);
});
