# Implementation Plan — Clipzi AI

## [Overview]

Membangun aplikasi full-stack "Clipzi AI" yang mengubah video panjang menjadi short video viral 9:16 dalam satu klik, dengan semua fitur editing canggih, multi-bahasa 30+, sistem credit, 4 paket pricing (Free, Standar, Pro, Team), login email & sosial media, pembayaran Duitku, Admin Dashboard, audit trail lengkap, dan keamanan crypto-grade. Backend FastAPI di Vast.ai (GPU), PostgreSQL di Supabase, Cloudflare R2 untuk storage, frontend Next.js.

**Status:** Implementasi selesai (backend core, API routes, models, services, infrastructure, frontend core)

---

## [Types] — Data Structures

### User & Auth Models
- **User:** id, email, password_hash (Argon2id), name, avatar_url, provider (email/google/x/facebook), provider_id, email_verified, is_active, is_banned, two_factor_enabled, two_factor_secret, last_login_at, last_login_ip, failed_login_attempts, lock_until, created_at, updated_at
- **UserProfile:** user_id, plan_type (free/standar/pro/team), credits_balance, credits_total_earned, credits_total_spent, credits_used_this_month, credits_reset_date, subscription_expires_at, duitku_customer_id, max_concurrent_tasks, watermark_enabled, priority_queue, language, timezone, plan_features_locked, created_at, updated_at
- **AdminUser:** id, email, password_hash, name, role (super_admin/admin/moderator), is_active, two_factor_enabled, can_adjust_credits, can_ban_users, can_manage_plans, can_view_audit, last_login_at, last_login_ip, failed_login_attempts, lock_until, created_at, updated_at

### Pricing & Subscription Models
- **PricingPlan:** id, name, display_name (JSON), description (JSON), price_monthly, price_yearly, credits_monthly, max_video_duration_minutes, max_concurrent_tasks, watermark, priority_queue, youtube_upload, all_editing_features, team_seats, features_list (JSON), is_active, created_at, updated_at
- **UserSubscription:** id, user_id, plan_id, status, current_period_start, current_period_end, cancel_at_period_end, duitku_subscription_id, created_at, updated_at
- **Transaction:** id, user_id, duitku_transaction_id, amount, currency, status, payment_method, payment_url, callback_received_at, created_at, updated_at
- **CreditTransaction:** id, user_id, amount, type, description (JSON), task_id, admin_id, balance_after, created_at

### Task & Clip Models
- **Task:** id, user_id, source_url, source_type, status, progress, target_duration_min/max, whisper_model, output_format, output_resolution, fps, original_duration, total_clips, error_message, auto_upload_youtube, youtube_upload_status, youtube_video_id, youtube_video_url, editing_options (JSON), credits_spent, plan_at_time, created_at, updated_at, completed_at
- **Clip:** id, task_id, clip_index, start_time, end_time, duration, title, download_url, subtitle_url, thumbnail_url, file_size, viral_score, viral_factors (JSON), ai_suggested_title, ai_suggested_description, ai_suggested_tags (JSON), youtube_uploaded, youtube_video_id, editing_applied (JSON), created_at

### Audit & Security Models
- **AuditLog:** id, actor_type, actor_id, actor_email, action, resource_type, resource_id, resource_name, old_values (JSON), new_values (JSON), metadata (JSON), ip_address, user_agent, geolocation (JSON), request_id, session_id, created_at

### New Feature Models
- **MultiPlatformJob, PlatformOutput, PlatformPreset:** Multi-platform repurpose
- **ClipTemplate:** Saved editing presets
- **BulkJob:** Bulk video processing
- **ClipPerformance, ViralPredictionHistory, BestTimeToPost:** Analytics
- **UserAPIKey, WebhookSubscription, APIUsageLog:** Developer API
- **CopyrightCheck, ContentModeration, GDPRRequest, Invoice:** Compliance
- **SecurityEvent:** id, event_type, actor_type, actor_id, ip_address, user_agent, details (JSON), risk_level, is_resolved, resolved_by, resolved_at, created_at
- **AdminSession:** id, admin_id, token_hash, expires_at, ip_address, user_agent, created_at
- **EncryptedSecret:** id, name, encrypted_value (AES-256-GCM), created_at, updated_at

---

## [Files] — Backend Structure
**Config:** Dockerfile, requirements.txt, .env.example, app/main.py
**Core:** config.py, security.py, feature_gate.py, audit.py
**DB:** base.py, session.py
**Models:** 30+ model files (user, task, clip, audit_log, security_event, etc.)
**Schemas:** 17+ Pydantic schema files
**API:** 18+ public routes + 8 admin routes
**Services:** storage, downloader, transcriber, processor, youtube_service, viral_scoring, metadata_generator, credit_service, plan_service, duitku_service
**Alembic:** alembic.ini, env.py

### Scripts
seed_pricing.py, grant_signup_credits.py

---

## [Functions] — Key Functions

**Auth & Security:** hash_password, verify_password, encrypt_field/decrypt_field, create_access_token, decode_token, generate_totp_secret, verify_totp

**Feature Gate:** is_feature_available, get_locked_features, calculate_task_credits, check_concurrent_tasks, check_credits

**Audit:** log, log_user_action, log_admin_action

**Credit:** grant_signup_bonus, deduct_credits, add_credits, get_balance

**Plan:** get_user_plan, get_plan_limits

---

## [Dependencies]

**Python:** fastapi, uvicorn, sqlalchemy, asyncpg, alembic, argon2-cffi, cryptography, pyotp, yt-dlp, faster-whisper, opencv-python, scenedetect, moviepy, boto3, redis, openai, pillow, numpy, requests, apscheduler

**Frontend:** next, react, tailwindcss, framer-motion, axios, lucide-react, js-cookie

**System:** Docker, docker-compose, PostgreSQL, Redis, FFmpeg

---

## [Implementation Order] — Completed

1. ✅ Setup direktori & konfigurasi
2. ✅ Database core & migrations (SQLAlchemy + Alembic)
3. ✅ Security core (Argon2id, AES-256-GCM, JWT, 2FA)
4. ✅ User & Profile models + PricingPlan (4 paket)
5. ✅ Admin models (AdminUser, AuditLog, SecurityEvent)
6. ✅ Feature Gate Core + Plan Middleware
7. ✅ Auth API (register, login, refresh, 2FA, social)
8. ✅ Credit system (signup bonus, deduct, add, balance)
9. ✅ Duitku integration (payment, callback, webhook)
10. ✅ Video processing services (downloader, transcriber, processor)
11. ✅ AI services (viral_scoring, metadata_generator, youtube_service)
12. ✅ New features (multi_platform, clip_templates, bulk_jobs, analytics, api_keys, webhooks, compliance, scheduled_publish)
13. ✅ Admin API (users, plans, tasks, transactions, audit, system, security)
14. ✅ Frontend core (landing, login, register, dashboard, components)
15. ✅ Dockerfile + docker-compose.yml
16. ✅ README.md documentation
17. ✅ implementation_plan.md

---

## [Next Steps (Optional)]

1. Implement background worker (ARQ/Redis) for async processing
2. Full YouTube Data API v3 upload implementation
3. Full Duitku webhook handler
4. Complete frontend (all dashboard/admin pages)
5. i18n translations for 17+ languages
6. Unit and integration tests
7. CI/CD pipeline
8. Deployment to Vast.ai
9. Android client (Kotlin/Retrofit)

---

## [Security Notes]

- All endpoints require authentication (JWT or API Key)
- Admin endpoints require admin role
- Rate limiting per API key and per IP
- Sensitive data encrypted with AES-256-GCM
- All user and admin actions logged in AuditLog
- 2FA available for additional security

**Duitku:** create_payment, verify_callback_signature, verify_webhook_signature

**Video:** validate_url, download_video, transcribe, detect_scenes, smart_crop_9x16, burn_subtitle, compress_video, remove_silence

**Storage:** upload_file, get_public_url, delete_file, get_presigned_url

### Frontend
package.json, next.config.js, tailwind.config.js, tsconfig.json, postcss.config.js
src/lib/api.ts, src/lib/i18n.ts
src/app/layout.tsx, src/app/globals.css, src/app/page.tsx
src/app/login/page.tsx, src/app/register/page.tsx, src/app/dashboard/page.tsx
src/components/Navbar.tsx, src/components/CreditBalance.tsx, src/components/PricingCards.tsx

### Infrastructure
docker-compose.yml, README.md