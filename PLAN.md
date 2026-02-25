# Plan: GicaTesis Offline Handling

## Problem
When GicaTesis is down, `/api/formats` returns 200 with cached data (no indication of offline state), while `/api/assets/logos/*` returns generic 502 errors. This creates an inconsistent experience: formats appear but logos break.

## Solution: Policy A "Offline Explicit" + Policy B "Strict Mode" (configurable)

Both policies implemented, switchable via `GICAGEN_STRICT_GICATESIS` env var.

---

## Implementation Steps

### Step 1: Add config setting
**File:** `app/core/config.py`
- Add `GICAGEN_STRICT_GICATESIS: bool` (default `False` → Policy A)

### Step 2: Add connectivity state tracker
**File (NEW):** `app/core/services/gicatesis_status.py`
- Singleton `GicaTesisStatus` with:
  - `online: bool` (default `True`)
  - `last_success_at: Optional[str]`
  - `last_error: Optional[str]`
  - `data_source: Literal["live", "cache", "demo", "none"]`
- Methods: `record_success()`, `record_failure(error)`, `to_dict()`
- Imported by format_service and router

### Step 3: Update FormatService to track state
**File:** `app/core/services/format_service.py`
- Import and use `GicaTesisStatus` singleton
- On successful sync: call `status.record_success()`
- On GicaTesisError (cache fallback): call `status.record_failure(str(e))`
- `list_formats()` returns existing dict (no JSON contract break)

### Step 4: Update router `/api/formats` (Policy A + B)
**File:** `app/modules/api/router.py`
- After getting result from `formats.list_formats()`:
  - **Policy B (strict):** If `result["stale"]` is True and `GICAGEN_STRICT_GICATESIS` → raise 503
  - **Policy A (default):** Return 200 with response headers:
    - `X-Data-Source: cache|live|demo`
    - `X-Upstream-Online: true|false`

### Step 5: Fix `/api/assets/{path}` — no more 502
**File:** `app/modules/api/router.py`
- Change `proxy_asset()`:
  - On `httpx.RequestError` → return 503 (not 502) with clear JSON detail
  - On upstream 4xx/5xx → return 503 with clear message
  - Import `GicaTesisStatus` — if known offline, immediately return 503 without even trying (avoid timeout waste)

### Step 6: Add `/api/gicatesis/status` endpoint
**File:** `app/modules/api/router.py`
- New endpoint `GET /api/gicatesis/status` → returns `gicatesis_status.to_dict()`
- Also embed gicatesis state in existing `GET /api/providers/status` response under a `gicatesis` key

### Step 7: Frontend — offline banner + asset guard
**File:** `app/static/js/app.js`
- In `loadFormats()`: read `X-Data-Source` and `X-Upstream-Online` headers from response
  - If `X-Upstream-Online === "false"`: show banner, use text fallback for logos (skip img loading)
- In `loadProviderStatus()`: also check `gicatesis` field for offline state
**File:** `app/templates/pages/app.html`
- Add hidden `<div id="gicatesis-offline-banner">` above formats grid (amber warning style)

### Step 8: Tests
**File (NEW):** `tests/test_gicatesis_offline.py`
- Test 1: `/api/formats` with mocked upstream failure + cache → 200 + correct headers (Policy A)
- Test 2: `/api/formats` with GICAGEN_STRICT_GICATESIS=true + failure → 503 (Policy B)
- Test 3: `/api/assets/logos/test.png` with upstream down → 503 (not 502)
- Test 4: `/api/gicatesis/status` reflects offline state
- Test 5: `/api/formats` with upstream success → 200 + X-Upstream-Online: true

### Step 9: Update .env.example
**File:** `.env.example`
- Add `GICAGEN_STRICT_GICATESIS=false` with comment

---

## Files Modified/Created Summary

| File | Action |
|------|--------|
| `app/core/config.py` | Add 1 setting |
| `app/core/services/gicatesis_status.py` | NEW — connectivity tracker |
| `app/core/services/format_service.py` | Use status tracker |
| `app/modules/api/router.py` | Headers on /formats, fix /assets, add /gicatesis/status |
| `app/static/js/app.js` | Offline banner + asset guard |
| `app/templates/pages/app.html` | Banner HTML element |
| `tests/test_gicatesis_offline.py` | NEW — 5+ tests |
| `.env.example` | Add GICAGEN_STRICT_GICATESIS |

## Non-breaking guarantees
- JSON response shape of `/api/formats` is unchanged (same `{formats, stale, cachedAt, source}`)
- Offline metadata communicated via HTTP headers (Policy A) only
- Policy B is opt-in via env var
- Frontend gracefully degrades: banner + text fallback for logos
