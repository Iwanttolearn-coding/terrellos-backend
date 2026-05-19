# Pastor AI Connect — Final Build Specification
**Version:** 1.0.0 — May 19, 2026
**Founder:** Terrell Millz
**Founder Emails:** millzterrell210@icloud.com · millzterrell5@gmail.com
**Live URL:** https://pastor-ai-connect.base44.app
**Backend:** https://terrellos-backend.onrender.com
**Repos:** eternal-echo (frontend) · terrellos-backend (FastAPI)

---

## 1. ARCHITECTURE

### Stack
- **Frontend:** React + Vite + Tailwind + Framer Motion · Deployed via Base44/Vercel
- **Backend:** FastAPI (Python) · Deployed on Render · Auto-deploy from `main` branch
- **AI:** OpenAI GPT-4o (text/theology/sermons) · DALL-E 3 (images) · Whisper (transcription)
- **Voice:** ElevenLabs TTS
- **Auth:** Base44 auth (`base44.auth.me()`)

### Environment Variables (Render)
```
OPENAI_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
FRONTEND_URL=https://heavenlyeternalecho.com
```

### API Rules
- All frontend API calls route through `src/lib/api.js` or `src/lib/terrellOS.js`
- Zero `safeInvoke` or `base44.functions.invoke` in production code
- All calls use direct `fetch()` to `https://terrellos-backend.onrender.com`
- 30-second timeout + graceful error handling on every request
- Cold-start handling: show "waking up" message, not error, when backend takes >6s

---

## 2. FOUNDER ACCESS — ALWAYS ENFORCED

```js
FOUNDER_EMAILS = ['millzterrell210@icloud.com', 'millzterrell5@gmail.com']
```

Founders always receive:
- Super Admin role
- Unlimited AI (all caps bypassed)
- All plans unlocked (Kingdom Pro features)
- All tools unlocked
- Founder badge display
- System diagnostics access
- Billing override (no charge)
- Feature override access

**Rule:** Every page that checks plan, role, or access MUST call `resolveUserAccess()` from `src/lib/founderAccess.js`. No page reads `user.plan` or `user.role` directly.

**Wrong email to remove everywhere:** `millsterrell5@gmail.com`
**Correct email:** `millzterrell5@gmail.com`

---

## 3. CHURCH PRICING STRUCTURE

### Free — Individual Believer
**Price:** $0 forever

**Includes:**
- Daily devotionals
- Bible reader (KJV + NIV)
- Limited sermon generation (3/month)
- Prayer journal · Scripture lookup
- Easy OBM Bible mode
- Limited AI chats (10/day)
- Community features
- Christian humor intro

**Limits:** No church dashboard · No voice cloning · No sermon archives · AI capped daily

---

### Small Church Plan
**Price:** $99/month
**Best for:** Churches up to 25 members

**Includes:**
- Pastor dashboard
- Sermon builder (unlimited)
- AI Bible studies · Devotional automation
- Prayer management · Attendance tools
- Church announcements · Multi-device access
- Sermon archive · KJV + 6 Bible translations
- Moderate AI generations/month · Denominational studies

---

### Growth Church Plan
**Price:** $299/month
**Best for:** Churches 25–150 members

**Includes everything in Small Church, plus:**
- Increased AI limits · Voice sermon assistant
- Advanced Bible lesson generation
- Team accounts (up to 5)
- Ministry workflows · Member engagement analytics
- Christian history library · Ancient texts library
- Apologetics institute · Church management tools
- Live transcription · Easy OBM Bible (all modes)

---

### Kingdom Pro Plan
**Price:** $2,000 lifetime license OR $799/year maintenance
**Best for:** Large ministries / organizations

**Includes everything in Growth, plus:**
- Full platform ownership access
- Priority AI processing · White-label branding
- Unlimited staff accounts · Founder-tier feature access
- Priority support · Advanced integrations
- Offline ministry package
- Corrections/chaplain edition support
- Voice cloning · Full sermon/media archive
- Fair-use AI protection (high but protected)

---

### Business Rules
- Never give unlimited AI to free users
- Monthly token/message caps per plan
- Fair-use protection — track AI usage per church
- Churches can upgrade anytime
- Lock premium sermon generation behind paid plans
- Keep onboarding friction LOW
- Allow free trial for churches (14 days on Growth)
- Simple, ministry-friendly billing

---

## 4. ROUTES & PAGES

### Core
| Route | Page | Status |
|---|---|---|
| `/` | Home / Landing | ✅ |
| `/founder` | Founder Center | ✅ |
| `/pricing` | Church Pricing | ✅ |
| `/billing` | Plan & Billing Status | ✅ |
| `/dashboard` | Main Dashboard | ✅ |
| `/settings` | Settings | ✅ |

### Theology & Study
| Route | Page | Status |
|---|---|---|
| `/sermon-prep` | Sermon Builder | ✅ |
| `/bible-study` | AI Bible Study | ✅ |
| `/denominations` | Denominational Studies | ✅ |
| `/apologetics` | Apologetics Institute | ✅ |
| `/church-history` | Church History | ✅ |
| `/discipleship` | Discipleship Center | ✅ |
| `/leadership-training` | Leadership Training | ✅ |
| `/theology` | Theology Hub | ✅ |

### Ancient Texts — NEW
| Route | Page | Status |
|---|---|---|
| `/ancient-texts` | Ancient Texts Library | ✅ |

**Sections inside `/ancient-texts`:**
- Dead Sea Scrolls Library (6 key scrolls)
- Book of Enoch — 1 Enoch, 2 Enoch, 3 Enoch
- Jubilees
- Testaments of the Twelve Patriarchs
- Apocrypha (7 books, labeled by canon)
- Pseudepigrapha
- Early Church Writings (Didache, Ignatius, Polycarp, etc.)
- Qumran Community History
- Essene Background & Theology
- Ancient Manuscript Comparisons

**AI Study buttons per text:** Overview · Bible Connections · Pastoral Application · Apologetics

**Disclaimer (permanent, always visible):**
> "This section includes ancient Jewish and Christian historical writings. Some are not accepted as Scripture by all denominations. Pastor AI clearly distinguishes between Bible canon, Apocrypha, historical writings, and theological commentary. These texts are provided for scholarly, historical, and apologetics research only."

**Canon labeling system (enforced in every AI prompt):**
- `canonical` — This text IS part of the accepted biblical canon
- `apocrypha` — Accepted by Catholic/Orthodox; NOT in Protestant or Jewish Bibles
- `pseudepigrapha` — Ancient writing; NOT accepted as Scripture by any major tradition
- `historical` — Valuable for scholarship; NOT Scripture
- `early-church` — Important historically; NOT Scripture or equal to the Bible
- `non-canonical` — Not part of any accepted Bible canon

**Non-negotiable rule:** Pastor AI must NEVER mix the Book of Enoch, Dead Sea Scrolls, Apocrypha, or other ancient writings into Bible doctrine without clearly labeling them as historical/non-canonical. This label is injected into every AI system prompt automatically.

---

### Easy OBM Bible — NEW
| Route | Page | Status |
|---|---|---|
| `/easy-bible` | Easy OBM Bible Mode | ✅ |

**Purpose:** Simple language Bible explanations for everyone — no seminary background required.

**Reading Modes:**
- 📖 Easy Read — Simple, clear language for everyone
- 🌱 New to the Bible — "Explain like I just started" mode
- ⭐ Children / Youth — Kid-friendly, ages 6–12
- 🕊️ Prison Ministry — Hope, redemption, new beginnings
- 🌅 Daily Devotional — Short, personal, encouraging
- 📢 Plain Sermon Prep — Simple outline from any verse

**Action buttons per passage (9 total):**
1. Read Full Bible Text
2. Explain Easy
3. Deep Study
4. Historical Context
5. Original Language
6. Denominational Views
7. Sermon Outline
8. Prayer From This Passage
9. Save to Notes

**Features:**
- Spanish / English toggle on every action
- 12 quick-passage chips (John 3:16, Psalm 23, etc.)
- Session-based saved notes panel
- Verse-by-verse breakdown mode

---

### Other Pages
| Route | Page | Status |
|---|---|---|
| `/eternal-echo` | Eternal Echo Memorial | ✅ |
| `/prayer` | Prayer Journal | ✅ |
| `/research/freemasonry` | Freemasonry Research | ✅ |
| `/ancient-texts` | Ancient Texts Library | ✅ |
| `/easy-bible` | Easy OBM Bible Mode | ✅ |

---

## 5. BACKEND ROUTES (43 total)

### Core
- `GET /` · `GET /health` · `GET /status` · `HEAD /`

### Memory
- `POST /v1/memory/session/start` · `/frame` · `/audio` · `/transcript` · `/end`
- `GET /v1/memory/profile/{id}`
- `POST /v1/memory/transcribe` · `/consent` · `/export` · `/delete`
- `POST /v1/memory/voice/sample-count` · `/train` · `/clone`

### Images
- `POST /v1/images/generate` — DALL-E 3 cinematic scenes
- `POST /v1/images/memorial` — Sacred memorial imagery

### Chat & Companion
- `POST /chat` · `/v1/companion/respond` · `/v1/companion/voice` · `/v1/companion/voice/auto`

### Voice
- `POST /v1/voice/speak` (ElevenLabs TTS)

### Upload
- `POST /v1/upload`

### Admin
- `POST /v1/admin/check-grant` · `GET /v1/admin/stats`

### Sermons
- `POST /v1/sermons/generate` — 7-stage GPT-4o sermon engine
- `GET /v1/sermons/{id}`
- `POST /v1/content/sermon/analyze`

### Theology Engine
- `POST /v1/theology/bible-study`
- `POST /v1/theology/discipleship`
- `POST /v1/theology/denomination`
- `POST /v1/theology/church-history`
- `POST /v1/theology/martyr`
- `POST /v1/theology/christian-hero`
- `POST /v1/theology/apologetics`
- `POST /v1/theology/prayer`
- `POST /v1/theology/lesson-plan`

### Ancient Texts Engine — NEW
- `POST /v1/ancient-texts/study` — AI study with canonical status
- `POST /v1/ancient-texts/qumran` — Dead Sea Scrolls / Essene study

### Easy Bible Engine — NEW
- `POST /v1/easy-bible/explain` — All 7 action types, Spanish/English, all 6 modes
- `POST /v1/easy-bible/verse-breakdown` — Verse-by-verse with Big Picture summary

---

## 6. FOUNDER CENTER (/founder)

Live status cards (required):
- ✅/❌ Backend Online / Offline
- ✅/❌ Image AI Ready / Missing OPENAI_API_KEY
- ✅/❌ Whisper Transcription Ready / Missing OPENAI_API_KEY
- ✅/❌ ElevenLabs Voice Ready / Missing ELEVENLABS_API_KEY
- Last checked timestamp
- Open Backend Docs button → `https://terrellos-backend.onrender.com/docs`
- Test Image Route button → calls `/v1/images/generate`
- Test Transcribe Route button → calls `/v1/memory/transcribe`

---

## 7. ERROR HANDLING STANDARDS

- All API failures shown via toast or error card — never silent
- Backend offline → show "Backend waking up, try again in 30s" (not generic error)
- Missing OPENAI_API_KEY → show labeled "Image AI: Missing API Key" card
- Missing ELEVENLABS_API_KEY → show labeled "Voice: Missing API Key" card
- All components wrapped in ErrorBoundary
- No white-screen crashes

---

## 8. CONSENT & PRIVACY (ETERNAL ECHO / MEMORY)

- Zero camera or microphone activation without explicit user consent
- ConsentGate must appear before any recording feature
- Consent stored in LegacyConsent entity with full audit fields
- Memory schema: MemoryProfile → MemorySession → StoryFragment
- All memory data follows structured schema — no unstructured chat logs
- Privacy-first, consent-driven architecture — non-negotiable

---

## 9. ANCIENT TEXTS — CANONICAL RULE (HARDCODED)

This rule is injected into every AI system prompt that touches non-canonical texts:

> "IMPORTANT DISCLAIMER: This content is for scholarly and historical research. It clearly distinguishes between canonical Scripture, Apocrypha, historical writings, and theological commentary. Never treat non-canonical texts as equal to the Bible without explicit labeling."

**Violation = build failure.** Any AI response that presents Enoch, Dead Sea Scrolls, Apocrypha, or Pseudepigrapha as Scripture without a canonical status label must be rejected.

---

## 10. DEPLOYMENT CHECKLIST

### Render (Backend)
- [ ] `OPENAI_API_KEY` set
- [ ] `ELEVENLABS_API_KEY` set
- [ ] `ELEVENLABS_VOICE_ID` set
- [ ] `FRONTEND_URL=https://heavenlyeternalecho.com` set
- [ ] Auto-deploy from `main` branch enabled
- [ ] `/status` returns 200 after deploy

### Vercel / Base44 (Frontend)
- [ ] `VITE_API_URL=https://terrellos-backend.onrender.com` set
- [ ] `vercel.json` rewrites pointing to `index.html` (React Router support)
- [ ] All routes return 200
- [ ] No `safeInvoke` or `base44.functions.invoke` in production bundle
- [ ] Founder emails have full access on first login

---

*Last updated: May 19, 2026 — Terrell Millz / TerrellOS*
