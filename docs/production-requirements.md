# Production Requirements — Web Quản Lý Tài Liệu Học Tập Thông Minh (Zero-Cost Free Tier Stack)

## 1. Scope & Target Audience
* **Deployment Scope:** Internet công khai (Public-facing) — Giới hạn đăng nhập bằng Email trường/xác thực Google SSO.
* **Target Users (3-6 tháng):**
  * Total Users: ~100 người dùng.
  * Peak Concurrent Users (CCU): ~10-20 người cùng lúc.

## 2. Resource & Storage Limits (Maximized Free Tier)
* **File Size Limit:** Tối đa 15MB / file PDF (Phù hợp tài liệu học tập, slide).
* **Storage Projection (3-6 tháng):** ~10GB trên Cloudflare R2 (Tận dụng 100% Free Tier 10GB, $0 Egress fees).
* **User Storage Quota:** Tối đa 100MB / tài khoản (~10-20 file PDF/người).
* **Document Processing Limit:** Max 50-80 trang / file PDF (tránh vượt timeout backend free).

## 3. Infrastructure & Deployment Architecture (Free Stack)
* **Frontend Hosting:** Vercel (Next.js/React) - Free Plan (100GB Bandwidth).
* **Backend Hosting:** Render / Koyeb (FastAPI container - Free Instance 512MB RAM).
* **Database:** Supabase hoặc Neon.tech (PostgreSQL Free Tier 500MB + `pgvector`).
* **Cache & Rate Limiting:** Upstash Redis (Free Tier 10k requests/ngày).
* **Object Storage:** Cloudflare R2 (10GB Free Storage, Free Egress).
* **AI Provider (Gemini API):**
  * Budget Cap: **$0 / tháng** (Hoàn toàn sử dụng Free Tier qua Google AI Studio).
  * Rate Limits: Tối đa 15 request/phút (RPM).
  * Per-user Limit: Tối đa 20 lượt hỏi AI / user / ngày (dùng Upstash Redis để enforce).

## 4. Data Retention & Privacy
* **Soft Delete:** File bị xóa giữ 14 ngày trước khi xóa cứng trên Cloudflare R2 để giải phóng dung lượng Free Tier.
* **Orphan File Cleanup:** Worker quét định kỳ hàng tuần để dọn dẹp các file rác không có liên kết DB.

## 5. Service SLA & Limits (Acceptable Free Constraints)
* **Cold Start Acceptable:** Chấp nhận Backend bị delay 30-50s ở request đầu tiên sau thời gian không hoạt động (do Render Free Instance 'sleep').
* **RTO (Recovery Time Objective):** < 12 giờ.
* **RPO (Recovery Point Objective):** < 24 giờ (Backup DB metadata thủ công hoặc dùng script export định kỳ).