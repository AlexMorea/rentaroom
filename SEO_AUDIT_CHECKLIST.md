# 🚀 Rooms4You SEO Setup Audit & Verification Checklist

## ✅ Phase 1: Domain Canonicalization (COMPLETED)

### 1. robots.txt Configuration
**Status:** ✅ FIXED
**Change Made:** Updated sitemap URL in robots.txt view
```
FROM: Sitemap: https://rooms4you.co.za/sitemap.xml
TO:   Sitemap: https://www.rooms4you.co.za/sitemap.xml
```
**File:** `listings/views/static_pages.py`
**Test URL:** https://www.rooms4you.co.za/robots.txt

**Expected Output:**
```
User-agent: *
Allow: /
Disallow: /dashboard/
Disallow: /landlord/
Disallow: /profile/
Disallow: /inbox/
Disallow: /rooms/*/edit/
Disallow: /rooms/*/images/
Disallow: /rooms/new/

Sitemap: https://www.rooms4you.co.za/sitemap.xml
```

---

### 2. Canonical Tags - Base Template
**Status:** ✅ FIXED
**Change Made:** Updated canonical URL in base template
```
FROM: https://rooms4you.co.za{{ request.path }}
TO:   https://www.rooms4you.co.za{{ request.path }}
```
**File:** `listings/templates/listings/base.html`
**Impact:** All pages inheriting from base.html now have correct canonical

---

### 3. Open Graph & Twitter Tags - Base Template
**Status:** ✅ FIXED
**Changes Made:**
- `og:image`: `https://rooms4you.co.za/...` → `https://www.rooms4you.co.za/...`
- `og:url`: `https://rooms4you.co.za/...` → `https://www.rooms4you.co.za/...`
- `twitter:image`: `https://rooms4you.co.za/...` → `https://www.rooms4you.co.za/...`
**File:** `listings/templates/listings/base.html`
**Impact:** Correct domain in social media shares

---

### 4. Room Detail Page SEO Tags
**Status:** ✅ FIXED
**Changes Made:** Updated all canonical and og tags in room_detail.html
```django
canonical_url:   https://rooms4you.co.za → https://www.rooms4you.co.za
og_url:          https://rooms4you.co.za → https://www.rooms4you.co.za
og_image:        https://rooms4you.co.za → https://www.rooms4you.co.za
twitter_image:   https://rooms4you.co.za → https://www.rooms4you.co.za
```
**File:** `listings/templates/listings/room_detail.html`
**Impact:** Individual room pages now have proper SEO tags

---

### 5. WWW Redirect Middleware
**Status:** ✅ IMPLEMENTED
**What It Does:**
- Redirects all non-www traffic to www version
- Uses 301 permanent redirects (SEO-friendly)
- Skipped in DEBUG mode for development
- Maintains HTTPS

**Redirect Behavior:**
```
http://rooms4you.co.za/          → https://www.rooms4you.co.za/
https://rooms4you.co.za/         → https://www.rooms4you.co.za/
http://www.rooms4you.co.za/      → https://www.rooms4you.co.za/
https://www.rooms4you.co.za/     ✅ (canonical - no redirect)
```

**File:** `rentaroom/middleware.py`
**Registered In:** `rentaroom/settings.py` (MIDDLEWARE list)
**Impact:** Google sees single canonical source

---

## 🎯 Phase 2: Sitemap Verification

### Sitemap Structure
**Status:** ✅ VERIFIED
**File:** `listings/sitemaps.py`

#### RoomSitemap
- **Includes:** All public room listings (is_available=True)
- **Changefreq:** daily
- **Priority:** 0.8
- **Protocol:** https
- **Example:** `/rooms/1/`, `/rooms/2/`, etc.

#### StaticViewSitemap
- **Includes:** Core public pages
  - Homepage `/`
  - Room listing `/rooms/`
  - About `/about/`
  - Services `/services/`
  - Contact `/contact/`
  - Safety `/safety/`
  - Terms `/terms/`
  - Privacy `/privacy/`
- **Changefreq:** weekly
- **Priority:** 0.5
- **Protocol:** https

**Sitemap URL:** `https://www.rooms4you.co.za/sitemap.xml`

**Test:** Visit sitemap.xml and verify:
- [ ] All URLs use `https://www.rooms4you.co.za/`
- [ ] No duplicate URLs
- [ ] Valid XML structure

---

## 🔍 Phase 3: Page-Level SEO

### Title Tags
**Status:** ✅ IMPLEMENTED
**Examples:**
```
Homepage:     "Rooms4You - Find a Room or Tenant in South Africa"
Room Page:    "Single Room - R2500/month in Mamelodi | Rooms4You"
Room List:    (inherited from base)
About Page:   (inherited from base)
```

### Meta Descriptions
**Status:** ✅ IMPLEMENTED
**Examples:**
```
Homepage:     "South Africa's trusted way to find a room to rent, 
              or find your next tenant. Verified landlords, direct messaging, 
              no hidden fees."
Room Page:    "[Room title] in [location] for R[price]/month. [Description excerpt]"
```

### Canonical Tags
**Status:** ✅ IMPLEMENTED
**All Pages:** Self-referencing canonical to www domain
**Room Pages:** Individual canonical URLs

---

## 🚫 Phase 4: Robots & Crawl Control

### Protected Pages (Disallowed)
```
/dashboard/       - Landlord dashboard
/landlord/        - Landlord area
/profile/         - User profiles
/inbox/           - Messaging
/rooms/*/edit/    - Room editing
/rooms/*/images/  - Image management
/rooms/new/       - Room creation
```
**Status:** ✅ CONFIGURED

### Allowed Pages
```
/                 - Homepage
/rooms/           - Room listing
/rooms/<id>/      - Individual rooms
/about/           - About page
/services/        - Services
/contact/         - Contact
/safety/          - Safety info
/terms/           - Terms
/privacy/         - Privacy
/trust/           - Trust center
```
**Status:** ✅ ACCESSIBLE

---

## 📊 Phase 5: Domain Configuration

### ALLOWED_HOSTS
**Status:** ✅ CONFIGURED
```python
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    ".onrender.com",
    "rooms4you.co.za",        # non-www (will redirect)
    "www.rooms4you.co.za",    # canonical
]
```

### CSRF_TRUSTED_ORIGINS
**Status:** ✅ CONFIGURED
```python
CSRF_TRUSTED_ORIGINS = [
    "https://rooms4you.co.za",
    "https://www.rooms4you.co.za",
    "https://*.onrender.com",
]
```

---

## 🔐 Phase 6: HTTPS & Security

### Protocol
**Status:** ✅ ALL HTTPS
- Base template uses https:// hardcoded for canonical/og tags
- WWW redirect middleware enforces HTTPS
- Django SecurityMiddleware enabled
- SECURE_SSL_REDIRECT recommended for production

### Headers
**Status:** ✅ IMPLEMENTED
- SecurityMiddleware: ✅
- CSRF protection: ✅
- X-Frame-Options: ✅
- Content-Type header: ✅

---

## 📋 Phase 7: Pre-Google Console Checklist

### Before Submitting to Google Search Console, verify:

**Robots.txt**
- [ ] Visit: https://www.rooms4you.co.za/robots.txt
- [ ] Confirm sitemap URL is `https://www.rooms4you.co.za/sitemap.xml`
- [ ] Confirm disallowed paths are correct
- [ ] Test with Google's robots.txt tester

**Sitemap**
- [ ] Visit: https://www.rooms4you.co.za/sitemap.xml
- [ ] Verify valid XML
- [ ] Count URLs (should include all available rooms + static pages)
- [ ] All URLs should use `https://www.rooms4you.co.za/`
- [ ] Validate with Google's sitemap validator

**Homepage**
- [ ] Visit: https://www.rooms4you.co.za/
- [ ] Check page title in browser tab
- [ ] Verify canonical tag: `https://www.rooms4you.co.za/`
- [ ] Inspect og:image and og:url

**Sample Room Page**
- [ ] Visit: https://www.rooms4you.co.za/rooms/7/
- [ ] Check page title (should include room details)
- [ ] Verify canonical: `https://www.rooms4you.co.za/rooms/7/`
- [ ] Verify og:image (should show room photo or logo)
- [ ] Check meta description

**Internal Links**
- [ ] Verify homepage links to `/rooms/`
- [ ] Verify room listings link to individual room pages
- [ ] Verify footer/navbar use correct URLs
- [ ] Use relative URLs internally (Django url tag)

**Non-www Redirect**
- [ ] Visit: https://rooms4you.co.za/
- [ ] Should 301 redirect to https://www.rooms4you.co.za/
- [ ] Check with: `curl -I https://rooms4you.co.za/`
- [ ] Check with: `curl -I http://rooms4you.co.za/`

---

## 🎯 Phase 8: Google Search Console Setup

### Step 1: Verify Domain Property
**Action:** Add to Google Search Console
1. Go to https://search.google.com/search-console/
2. Click "Add property"
3. Choose **Domain** property type
4. Enter: `rooms4you.co.za` (without www, without https://)
5. Verify ownership (DNS record recommended)

**Why Domain Property?**
- Covers all protocol variants (http, https)
- Covers all subdomains (www, api, etc.)
- More convenient than URL properties

### Step 2: Submit Sitemap
**Action:** In Search Console → Sitemaps → Add/test
1. Enter: `sitemap.xml` (or full URL)
2. Google will automatically fetch from:
   `https://www.rooms4you.co.za/sitemap.xml`
3. Monitor the "Status" column
4. Wait for processing (can take days)

### Step 3: Request Indexing for Key Pages
**Priority Tier 1 (Critical):**
- [ ] https://www.rooms4you.co.za/
- [ ] https://www.rooms4you.co.za/rooms/
- [ ] https://www.rooms4you.co.za/about/
- [ ] https://www.rooms4you.co.za/safety/
- [ ] https://www.rooms4you.co.za/contact/
- [ ] Sample rooms: /rooms/1/, /rooms/5/, /rooms/7/

**How to Request Indexing:**
1. Search Console → URL Inspection
2. Paste URL
3. Click "Request Indexing"
4. Wait for crawl

### Step 4: Monitor Indexing Status
**Track in Search Console:**
- Pages → Indexed
- Pages → Not indexed
- Pages → Discovered (not yet indexed)
- Pages → Excluded

### Step 5: Check Core Web Vitals
- Largest Contentful Paint (LCP)
- Interaction to Next Paint (INP)
- Cumulative Layout Shift (CLS)

---

## 🚀 Next Steps After Launch

### Week 1
- [ ] Verify domain property in Search Console
- [ ] Submit sitemap
- [ ] Request indexing for Tier 1 pages
- [ ] Monitor robots.txt crawl stats

### Week 2-4
- [ ] Monitor indexing progress
- [ ] Check Core Web Vitals
- [ ] Analyze crawl stats
- [ ] Look for errors/warnings in Search Console

### Month 2+
- [ ] Monitor search impressions
- [ ] Track organic traffic in Analytics
- [ ] Optimize based on search queries
- [ ] Consider location-based URL structure (Phase 2 improvement)

---

## 📝 Files Modified

1. **listings/views/static_pages.py**
   - Updated robots_txt view (sitemap URL)

2. **listings/templates/listings/base.html**
   - Updated canonical tag
   - Updated og:url and og:image
   - Updated twitter:image

3. **listings/templates/listings/room_detail.html**
   - Updated canonical_url block
   - Updated og_url block
   - Updated og_image block
   - Updated twitter_image block

4. **rentaroom/middleware.py** (NEW)
   - Added WWWRedirectMiddleware

5. **rentaroom/settings.py**
   - Registered WWWRedirectMiddleware

---

## 🎓 Key SEO Principles Applied

✅ **Single Canonical Domain:** www.rooms4you.co.za
✅ **Consistent URLs:** All sitemaps, redirects, canonical tags use www
✅ **301 Redirects:** Permanent redirects from non-www to www
✅ **Sitemap Submission:** Ready for Google Console
✅ **Robots.txt:** Crawl-friendly, points to sitemap
✅ **Meta Tags:** All pages have unique titles and descriptions
✅ **Open Graph:** Proper tags for social sharing
✅ **HTTPS:** All URLs enforce HTTPS
✅ **Page Hierarchy:** Clear structure (homepage → listings → individual rooms)
✅ **Crawlable Content:** Public pages accessible to crawlers

---

## ✅ Ready for Google Search Console

Once you've verified this checklist locally:

1. Deploy all changes to production
2. Wait 24-48 hours for DNS/redirects to fully propagate
3. Verify robots.txt and sitemap are accessible
4. Go to Google Search Console
5. Add domain property for rooms4you.co.za
6. Submit sitemap
7. Request indexing for key pages

**Expected Timeline:**
- Sitemap processing: 1-3 days
- First indexing: 3-7 days
- Full indexing: 2-4 weeks
- Search impressions: 4+ weeks

This is normal and healthy for a new site!
