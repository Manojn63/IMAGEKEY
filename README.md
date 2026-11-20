# IMAGEKEY — Optical Vault Platform

> **Core Mission**: `CREATE/UPLOAD IMAGE → REGISTER & HASH IMAGE → SHARE IMAGE → SCAN/UPLOAD IMAGE → RECOGNIZE IMAGE → DISPLAY TIERED INFORMATION`

**IMAGEKEY** is a production-grade, full-stack, zero-trust image-based information-sharing platform. It transforms physical logos, packaging graphics, and branding art into cryptographically anchored **Optical Keys** that serve as secure, high-tech alternatives to standard QR codes.

---

## 🏛️ System Architecture & Workflow

```text
================================================================================
                        1. IMAGE OWNER WORKFLOW (REGISTRATION)
================================================================================
  [User Registration / Login] 
               │
               ▼ (JWT Bearer / HTTP-Only Session Cookie)
  [Upload Image (Logo / Packaging)] ──► (File Sanitization: Real MIME, <=5MB, Strip EXIF)
               │
               ▼
  [Attach Tiered Information]
     ├──► Public Info (Title, Description, Website, Email, Phone, Services)
     └──► Tier 2 Private Vault (Confidential Notes, Internal Data JSON, Docs)
               │
               ▼
  [Backend Vision Processing (Pillow + ImageHash + OpenCV ORB)]
     ├──► Cryptographic Public Image ID (secrets: IMG-XXXXXXXX)
     ├──► Perceptual Hash (pHash) & Difference Hash (dHash)
     └──► OpenCV ORB Feature Descriptors (raw uint8 byte serialization, no pickle)
               │
               ▼
  [Persist to PostgreSQL / SQLite] (7 ORM Tables)
               │
               ▼
  [Share Registered Image] (Print, Packaging, Digital, Merchandising)

================================================================================
                       2. RECEIVER WORKFLOW (SCAN & VERIFY)
================================================================================
  [Open Optical Scanner] (WebRTC Camera / File Drag-and-Drop)
               │
               ▼
  [Two-Tier Computer Vision Engine]
     ├──► Stage 1: Fast Hamming Distance Pre-Filter (pHash & dHash)
     └──► Stage 2: OpenCV ORB BFMatcher + Lowe's Ratio Test (k=2, ratio=0.75)
               │
               ▼
  [Calibrated Confidence Meter]
     ├──► >= 85%: VERIFIED_MATCH ──► Display Public Metadata Preview
     ├──► 65% - 84%: UNCERTAIN   ──► Interactive Guidance (Lighting / Glare)
     └──► < 65%: NO_MATCH        ──► Clean Zero-Trust Rejection
               │
               ▼
  [Tier 2 Private Vault Access Attempt]
     ├──► Authorized (Owner / Admin / Active ImagePermission) ──► Decrypt & Unlock
     └──► Unauthorized / Anonymous ──► Log Incident & 403 Forbidden Shield State
```

---

## 📑 Complete 10-Page Frontend Directory

All 10 user-facing and administration pages are built using the **"Optical Vault"** design system (Light and Dark mode with glassmorphic cards and cyan/electric-blue neon accents):

| # | Route | Page Title | Access Clearance | Core Capabilities |
|---|-------|------------|------------------|-------------------|
| **1** | `GET /` | **Landing Page** | Public | Hero showcase, interactive architecture diagram, live system telemetry. |
| **2** | `GET /auth/login`<br>`GET /auth/register` | **Authentication Vault** | Public / Guest | Dual-mode login & registration with JWT tokens and HTTP-only session cookies. |
| **3** | `GET /dashboard` | **User Asset Dashboard** | Authenticated | Asset stats, registered optical keys grid, quick actions for public/private views. |
| **4** | `GET /register-image` | **Register Image & Hash** | Owner / Admin | Drag-and-drop upload, real-time preview, EXIF stripping, pHash & ORB extraction. |
| **5** | `GET /images/{uid}/edit` | **Image Info Editor** | Owner / Admin | Dual-tab editor for Public Metadata (Tab 1) and Encrypted Private Vault (Tab 2). |
| **6** | `GET /scan` | **Optical Vault Scanner** | Public | Live WebRTC camera viewfinder with HUD brackets, laser sweep, and drag-and-drop. |
| **7** | `GET /public/{uid}` | **Public Information View** | Public | Open verified metadata, company attribution, contact channels, and private vault CTA. |
| **8** | `GET /vault/{uid}` | **Protected Private Vault** | Authorized | Locked shield state for unauthorized guests; unlocks confidential notes & JSON store. |
| **9** | `GET /images/{uid}/permissions` | **Permission Manager** | Owner / Admin | Granular access control by email (`view_private` / `edit`), expiry dates, one-click revoke. |
| **10** | `GET /admin` | **Admin Operations Hub** | Admin Only | Global platform KPIs, user moderation, image catalog suspension, and audit logs. |

---

## 🗄️ Database Architecture (7 SQLAlchemy Models)

The database schema is fully agnostic, running seamlessly on **PostgreSQL** in production and **SQLite (`aiosqlite`)** in memory for automated testing:

1. **`users`**: UUID primary keys, unique emails, bcrypt password hashes, and RBAC roles (`admin`, `owner`, `viewer`).
2. **`companies`**: Verified organizational branding linked to business owners.
3. **`registered_images`**: Public UID (`IMG-XXXXXXXX`), file paths outside web root, pHash string, dHash string, OpenCV ORB descriptor raw bytes (`LargeBinary`), and status (`active`, `suspended`).
4. **`public_information`**: Open metadata (title, description, website URL with HTTP/HTTPS validation, contact email, phone, services JSON tags).
5. **`private_information`**: Tier 2 confidential records (confidential notes, internal data JSON key-value store, and document reference paths).
6. **`image_permissions`**: Granular role-based permissions (`view_private` / `edit`) granted to target users by email with optional expiration timestamps.
7. **`access_logs`**: Immutable security audit trail recording action types (`scan_success`, `scan_fail`, `view_public`, `view_private`, `unauthorized_attempt`, `permission_change`), client IPs, user agents, and confidence scores.

---

## 🛡️ Security Hardening & Zero-Trust Defense

* **Polyglot & Malware Neutralization:** All uploaded images are validated for real MIME types (`JPEG`, `PNG`, `WEBP`) and re-encoded via Pillow, permanently discarding all EXIF and metadata blocks.
* **No `pickle` Serialization:** OpenCV ORB feature descriptors are converted directly to raw NumPy `uint8` byte buffers (`tobytes()`), eliminating remote code execution attack vectors.
* **Zero-Trust Information Isolation:** Scanning or publicly querying an image returns exclusively `public_information`. Private vault records are queried only upon authenticated clearance verification.
* **Defensive HTTP Headers Middleware:**
  * `X-Content-Type-Options: nosniff`
  * `X-Frame-Options: DENY`
  * `Referrer-Policy: strict-origin-when-cross-origin`
  * `Permissions-Policy: camera=(self)`
* **Rate Limiting (`slowapi`):**
  * `POST /api/v1/auth/login`: `10/minute`
  * `POST /api/v1/auth/register`: `5/minute`
  * `POST /api/v1/scanner/identify`: `30/minute`
  * Automatically disabled during pytest execution (`TESTING=1`) to prevent test flakiness.

---

## 🚀 Quickstart & Local Execution

### 1. Prerequisites
* Python 3.10+ (Tested on Python 3.14)
* Docker & Docker Compose (Optional for local PostgreSQL)

### 2. Environment Setup
```powershell
# Clone or navigate to the workspace
cd "c:\Users\manoj\Downloads\Image secret QR code"

# Create virtual environment (if not already created)
python -m venv venv

# Activate Virtual Environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install Dependencies
pip install -r requirements.txt
```

### 3. Database Initialization (Optional Docker PostgreSQL)
To run a local PostgreSQL instance via Docker Compose:
```bash
docker compose up -d
```
*(The platform automatically creates tables and runs in standalone SQLite mode if PostgreSQL is not active).*

### 4. Run the Development Server
```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open your browser:
* **Web Landing Page**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
* **Live Camera Scanner**: [http://127.0.0.1:8000/scan](http://127.0.0.1:8000/scan)
* **Register Image**: [http://127.0.0.1:8000/register-image](http://127.0.0.1:8000/register-image)
* **User Dashboard**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)
* **Admin Operations**: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
* **Interactive API Docs (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Automated QA & Verification Suite

To execute all 45 automated integration, security, and unit tests:

```powershell
.\venv\Scripts\pytest.exe tests/ -v
```

### Test Suite Summary:
* `tests/test_auth.py` (4 tests) — Registration, login, invalid JWT rejection, cookie auth.
* `tests/test_cors_and_static.py` (4 tests) — CORS whitelist, static assets, auth templates.
* `tests/test_health.py` (3 tests) — Landing page, health API, `/health` alias.
* `tests/test_images.py` (6 tests) — Owner upload, viewer rejection, 5MB limits, EXIF stripping.
* `tests/test_scanner.py` (7 tests) — Two-tier CV matching, compression tolerance, noise rejection.
* `tests/test_public_info.py` (7 tests) — Anonymous public display, owner updates, XSS URL rejection.
* `tests/test_private_vault.py` (8 tests) — Zero-trust access controls, expiration, permission revocation.
* `tests/test_admin_and_security.py` (6 tests) — Admin RBAC, moderation, security headers, rate limiting.

**Total: 45 passed out of 45 tests (100% pass rate).**
