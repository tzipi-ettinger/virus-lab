# תוכנית עבודה — מפתחת B (Backend + Frontend)

**נכתב עבור:** מפתחת B (אסתי). צפי (מפתחת A) תקבל עותק לעיון.
**תאריך:** 18.10.2026 · **הקפאת פיצ׳רים:** ג׳ 20.10 בערב · **הגשה:** ד׳ 21.10

## הקשר

ב־18.10 התעדכנו הנחיות האתגר (v2). התוצר הוא עכשיו **רשומות שנשמרות במערכת**: רשומה לכל התחייבות, תיקון ואישור, חזרה לרשומות, חיפוש וסינון, ותצוגה של מה אושר ומה ממתין. ייצוא לקובץ הפך לאופציונלי, והוחלט לוותר עליו.

בנוסף נדרשים **דומיין חי** ואבטחה ברמה שאפשר להציג ללקוח. לכן:

- **מסד הנתונים:** אושר מעבר מ־SQLite מקומי ל־**PostgreSQL**.
- **פריסה:** אושר **Docker על Render**.
- **התחברות:** משתמשים מוגדרים מראש, בלי תפקידים.
- **תשובות צפי:** ⏳ **עוד לא ענתה** על A1–A9 ([GUIDELINES-V2-CHANGES.md](GUIDELINES-V2-CHANGES.md) §9). התוכנית בנויה לפי ההצעות שבמסמך, וכל מה שנשען עליהן מסומן ⏳. מה כל תשובה משנה מפורט בסעיף 5.1א.

מצב הקוד היום: כמעט כל הקבצים הם שלד ריק. הקבצים הקיימים:

- **שכבת השמירה:** `backend/app/storage/schema.sql` ו־`db.py`, כתובים ל־SQLite.
- **טיוטת החוזה (PR #4, מוזגה):** `schemas/api.py` כולל `Record`, `RecordSummary`, `RecordList`, `RecordPatch`/`RecordPatchResponse`, `ApproveRequest`, `ExtractResponse` ו־`Problem` (עם `blocking_fields`). `api/records.py` מגדיר את ה־routes, שמחזירים `501` עד שיש שמירה וכללים.
- **קבצי האקסל** (`export/`, `api/export.py`, `api/validate.py`, `ExportButton`, `useValidate`) עדיין בריפו.
- **fixtures לכללים:** ארבעה קבצים ב־`backend/tests/fixtures/rules/`.
- **CI:** שלוש בדיקות פועלות: `backend`, `frontend` ו־`contract`.
- **הממשק:** תבנית Vite עם RTL.

---

## 1. סיכום: מה באחריות מפתחת B

**B אחראית על כל מה שקורה לנתונים מהרגע שהמודל החזיר תשובה, ועל התשתית שהמערכת רצה עליה:**

| תחום | באחריות B |
|---|---|
| כללים עסקיים | נרמול, ולידציה, `review_policy`, `apply_rules`, בניית רשומה לכל התחייבות, רשימת השולחים הסגורה |
| שמירה | סכמת Postgres, `db.py`, `repo.py`, שכבת השירות (שמירה, תיקון, אישור) ויומן ביקורת |
| API | `records`, `pages/{id}/image`, `senders`, `auth` |
| התחברות ואבטחה | משתמשים, סשנים, הגנה על כל ה־API, CSRF, כותרות אבטחה, הגבלת ניסיונות כניסה |
| תשתית | Dockerfile, `docker-compose` לפיתוח, Render + Postgres מנוהל, הדומיין, שינויי CI |
| Frontend | מעטפת האפליקציה וניווט (`App.tsx`), מסך כניסה, מסך בדיקה ואישור, מסך רשומות עם חיפוש וסינון, דף רשומה, `api/client.ts` |
| מדידה | `eval/run_eval.py`, דוח התוצאות |
| תיעוד | SPEC 0.3, PLAN, README (בתיאום) |

**איפה האחריות של B נגמרת. מפתחת A אחראית על:**

- **קליטה:** `ingest`, רסטריזציה וסיבוב
- **חילוץ:** Gemini, prompt, `assemble`, `pipeline/service.py`
- **ממשק:** `UploadPanel` ו־`DocumentPreview`
- **תמונת העמוד:** יצירת התמונה הדחוסה (JPEG)
- **endpoint החילוץ:** `POST /api/v1/extract`

**נקודות המגע עם A (לפי ההצעות ב־A1–A9, ⏳ ממתינות לתשובת צפי):**

1. **שמירת החילוץ (A2 ⏳):** A קוראת לפונקציה אחת של B בסוף כל עמוד: `save_extracted_page(...)`.
2. **תצוגת המקור (A1 ⏳):** `DocumentPreview` טוען את התמונה מ־URL של העמוד.
3. **החוזה:** `schemas/api.py` משתנה רק ב־PR משותף.

**קבצים משותפים ש־B צריכה לגעת בהם (A8 ⏳, רק אחרי אישור של צפי):**

- `main.py`
- `settings.py`
- `extract.py` / `service.py` (רק הקריאה לשמירה)
- `client.ts`
- `DocumentPreview.tsx` (רק מקור התמונה)
- `App.tsx`
- `CODEOWNERS`

---

## 2. Backend

### 2.1 מבנה תיקיות (רק מה ש־B מוסיפה או משנה)

```
backend/
├── app/
│   ├── api/
│   │   ├── auth.py            # login / logout / me                       (חדש)
│   │   ├── records.py         # records, pages/{id}/image, senders        (חדש)
│   │   ├── validate.py, export.py   → נמחקים
│   ├── auth/                  # (חדש)
│   │   ├── passwords.py       # hashlib.scrypt: hash + verify (בלי תלות חדשה)
│   │   ├── sessions.py        # יצירה, אימות, ביטול, תפוגה
│   │   └── deps.py            # require_user, check_origin (CSRF)
│   ├── rules/
│   │   ├── normalize.py, validators.py, review_policy.py, engine.py, senders.yaml
│   │   └── records.py         # build_records(form) → רשומה לכל התחייבות (חדש)
│   ├── storage/
│   │   ├── schema.sql         # מוסב ל-Postgres
│   │   ├── db.py              # pool חיבורים, init + בדיקת גרסת סכמה
│   │   ├── repo.py            # כל ה-SQL
│   │   └── service.py         # save_extracted_page, patch_record, approve_record (חדש)
│   ├── security.py            # middleware לכותרות אבטחה (חדש)
│   ├── keep_alive.py          # פנייה עצמית כל 10 דקות, כדי ש-Render לא ירדים את השרת (חדש)
│   └── export/                → נמחק
├── scripts/
│   ├── create_user.py         # יצירת משתמש / איפוס סיסמה (חדש)
│   └── seed_demo.py           # טעינה מחדש של נתוני הדגמה (חדש, רק קובצי האתגר)
├── eval/run_eval.py
Dockerfile, .dockerignore, docker-compose.yml   # בשורש הריפו (חדשים)
```

### 2.2 נקודות קצה

כל הנתיבים תחת `/api/v1` דורשים סשן תקף, חוץ מ־`login`. נתיב `/api/health` פתוח. הנתיבים בטבלה הם של B, אלא אם צוין אחרת.

| Method | Path | קלט | פלט / התנהגות |
|---|---|---|---|
| `POST` | `/api/v1/auth/login` | `{username, password}` | `204` ו־`Set-Cookie`. שגיאה כללית "שם משתמש או סיסמה שגויים" (`401`). חסימה זמנית אחרי 5 כישלונות (`429`) |
| `POST` | `/api/v1/auth/logout` | — | מבטל את הסשן ב־DB ומוחק את העוגייה (`204`) |
| `GET` | `/api/v1/auth/me` | — | `{username, display_name}`, או `401` |
| `GET` | `/api/v1/records` | `q, status, needs_review, sender, date_from, date_to, limit (ברירת מחדל 50, מקסימום 200), offset` | `RecordList {items: RecordSummary[], total, limit, offset}`. נוסיף `counts: {pending, approved, needs_review}` (B0.2) |
| `GET` | `/api/v1/records/{id}` | — | `Record` מלא |
| `PATCH` | `/api/v1/records/{id}` | `RecordPatch {version, fields?: {name: {value?, confirmed?}}, central_numbers?: [{idx?, value?, confirmed?}]}` | מריץ את הכללים מחדש לפי SPEC 7.4, שומר ומחזיר `RecordPatchResponse {record, siblings}`. שדה משותף מתעדכן גם ברשומות האחיות מאותו עמוד (A3 ⏳). `409 version_conflict` אם הגרסה ישנה. `409 record_approved` אם הרשומה מאושרת (A6 ⏳) |
| `POST` | `/api/v1/records/{id}/approve` | `{version}` | מריץ את הכללים מחדש. אם נשאר שדה מסומן: `409` מסוג `review_required` עם `blocking_fields: [...]`. אחרת `status=approved` ו־`approved_by` |
| `DELETE` | `/api/v1/records/{id}` | — | רק לרשומה ממתינה (A5 ⏳). מאושרת: `409` |
| `GET` | `/api/v1/pages/{page_id}/image` | — | JPEG, עם `Cache-Control: no-store` |
| `GET` | `/api/v1/senders` | — | הרשימה הסגורה (שמות קנוניים), לרשימה הנפתחת ולסינון |
| `POST` | `/api/v1/extract` | (A) | `{files, records, failed_pages}` (A1 ⏳). דורש סשן (D10 ⏳) |

**שגיאות:** פורמט `application/problem+json` אחיד (`errors.py`, SPEC 9.5) עם `type` קבוע שה־frontend יכול לזהות:

| קוד | `type` |
|---|---|
| `401` | `not_authenticated` |
| `403` | `csrf_rejected` |
| `404` | `not_found` |
| `409` | `version_conflict` / `review_required` / `record_approved` / `sibling_approved` |
| `422` | `validation` |
| `429` | `too_many_attempts` |

### 2.3 מודלים בחוזה (`schemas/api.py`, PR משותף)

**כבר מוזג כטיוטה (PR #4, A1 ⏳ עד שצפי מאשרת):**

- **`FormField`:** המבנה של SPEC 9.2: `raw`, `value`, `model_status`, `evidence`, `issues`, `needs_review`, `corrected`, `confirmed`.
- **`Form`:** המבנה הפנימי בין `assemble` ל־`apply_rules`. לא נשלח ב־HTTP.
- **`Record`:** `commitment_number` הוא שדה בודד, ו־`preview_image` יצא מהחוזה.
- **מודלים נוספים:** `RecordSummary`, `RecordList`, `RecordPatch` (עם `ListItemEdit` למרכזיים), `RecordPatchResponse {record, siblings}`, `ApproveRequest`, `ExtractResponse {files, records, failed_pages}`, `Problem {type, title, status, detail, blocking_fields}`.

**מה נשאר להוסיף (B0.2):**

- **התחברות:** `LoginRequest`, `Me`.
- **`Record`:** `approved_by`, `updated_by` (שם משתמש).
- **`RecordList`:** `counts`.
- **endpoints חדשים:** `DELETE /records/{id}` (A5 ⏳) ו־`GET /senders`.
- **מחיקה:** הקבצים של האקסל.

### 2.4 מסד נתונים (Postgres)

> **המסד הוא PostgreSQL. לא משתמשים ב־SQLite.** הוא מוזכר כאן רק כי קובצי השלד שכבר נמצאים בריפו (`schema.sql`, `db.py`, `test_db.py`) נכתבו ל־SQLite לפני ההחלטה על הפריסה. משימה B0.3 מחליפה אותם.
>
> **למה Postgres:**
> - **שמירת הנתונים:** דומיין חי מחייב מסד שהנתונים בו נשמרים גם כשהשרת מופעל מחדש. בשרת חינמי אין דיסק קבוע, ולכן קובץ SQLite היה נמחק.
> - **הפשטות:** Postgres של Render רץ באותו מקום כמו השרת ולא דורש התקנה. מקבלים כתובת חיבור אחת, ומקומית המסד רץ ב־`docker compose`.
> - **הקוד:** כל ה־SQL נמצא בקובץ אחד (`repo.py`), בלי ORM ובלי כלי migrations, כי מדובר ב־6 טבלאות ו־3 ימי עבודה.

**מה משתנה בהסבת השלד מ־SQLite:**

| SQLite | Postgres |
|---|---|
| `STRICT` | הוסר; הטיפוסים נאכפים בעמודות |
| `BLOB` | `BYTEA` |
| זמנים | `TIMESTAMPTZ` |
| `PRAGMA user_version` | טבלת `schema_meta(version)` |

כל המזהים נשארים `TEXT`, כדי לשמור על אפסים מובילים.

```
users(id PK, username UNIQUE, password_hash, display_name, is_active,
      failed_attempts INT, locked_until TIMESTAMPTZ, created_at, last_login_at)
sessions(token_hash PK, user_id → users, created_at, expires_at, last_seen_at)  -- נשמר רק hash של הטוקן
page(id PK, source_filename, page_number, rotation, created_at, created_by → users)
page_image(page_id PK → page ON DELETE CASCADE, mime, sha256, bytes BYTEA)
record(id PK, page_id → page CASCADE, commitment_idx, status CHECK(pending|approved),
       needs_review BOOL, version INT,
       national_id, commitment_number, central_numbers, first_name, last_name,
       sender, received_date DATE, search_text,
       created_at, updated_at, approved_at, approved_by → users,
       UNIQUE(page_id, commitment_idx))
record_field(record_id → record CASCADE, field, idx, raw, value, model_status, evidence,
             issues JSONB, needs_review, corrected, confirmed, updated_at,
             PK(record_id, field, idx))
record_event(id BIGSERIAL, record_id → record CASCADE, at, user_id, action, field, old, new)
schema_meta(version INT)
INDEX: record(status, received_date), record(national_id), record(commitment_number), record(page_id)
```

**חיבור:**

- **ספרייה:** `psycopg` 3 עם `psycopg_pool` (תלות חדשה, ראו החלטה D1).
- **pool:** נפתח ב־lifespan של האפליקציה, וכל בקשה מקבלת חיבור משלו.
- **כתובת החיבור:**
  - **השרת ב־Render:** מתחבר דרך ה־Internal Database URL, ברשת הפנימית של Render.
  - **מחוץ ל־Render** (למשל `create_user` מהמחשב): רק דרך ה־External URL, עם `sslmode=require`.
- **בדיקת סכמה:** אם גרסת הסכמה ב־DB לא תואמת לקוד, השרת לא עולה ומציג הודעה ברורה.

### 2.5 לוגיקה עסקית

**`apply_rules(form) -> form`** (טהורה, בלי I/O). זה הסדר:

1. **`normalize`**
   - **ת״ז:** לפי הטבלה ב־SPEC 5.2.
   - **תאריך:** ISO, ושנה דו־ספרתית הופכת ל־`20YY`.
   - **מרכזי:** ספרות בלבד, בלי כפילויות.
   - **התחייבות:** מעתיקים כמו שנכתב. כלל `^\d{3}/\d{6,}$` מסיר את הקידומת ומוסיף issue, ו־`raw` נשמר.
   - **שולח:** מיפוי לפי הכינויים ל־`senders.yaml`.
2. **`validators`:** ספרת ביקורת של ת״ז, תאריך קיים, טווח 2020 עד היום, מרכזי בן 6 ספרות.
3. **`review_policy`:** קודי ה־issues מ־SPEC 8. `needs_review` של שדה = יש לו warning **והוא לא `confirmed`**.

**כללי עריכה (SPEC 7.4):**

- `raw` לא משתנה אחרי החילוץ.
- עריכה קובעת `value` ו־`corrected=true`, ומבטלת `confirmed`.
- הנרמול רץ מ־`value` אם השדה תוקן, ואחרת מ־`raw`.
- `issues` ו־`needs_review` שמגיעים מהלקוח לא נלקחים בחשבון.

**`build_records(form)`:**

- רשומה לכל התחייבות, וכל המרכזיים מופיעים בכל רשומה. אין מכפלה בין מרכזיים להתחייבויות.
- טופס בלי התחייבות הופך לרשומה אחת עם `REQUIRED_MISSING`.

**`service.save_extracted_page(conn, form, image, user)`:** כל השלבים רצים בטרנזקציה אחת:

1. `apply_rules`
2. `build_records`
3. בדיקת כפילות (A4 ⏳): התחייבות שכבר קיימת ב־DB מקבלת `DUPLICATE_RECORD` (warning) על השדה `commitment_number`, כך ש־`confirmed` על השדה פותר את הסימון.
4. שמירה של העמוד, התמונה והרשומות.
5. רישום `record_event 'created'`.

עמוד שנכשל **לא נשמר** (A7 ⏳).

**`service.patch_record(...)`:**

- מעדכן עם `UPDATE … WHERE version=?`.
- מריץ את הכללים מחדש ומעדכן את העמודות לחיפוש ואת `search_text`.
- שדה משותף מתעדכן גם ברשומות האחיות שממתינות (A3 ⏳). אם יש אחות מאושרת: `409 sibling_approved` (החלטה D5).
- כל שינוי נרשם ב־`record_event`.

**`service.approve_record(...)`:**

- מריץ את הכללים מחדש.
- חוסם אם יש שדה עם `needs_review`, או issue ברמת הרשומה. שדה ריק שאושר (`confirmed`) נחשב מטופל.
- אין ביטול אישור (A6 ⏳).

**חיפוש:**

- **`search_text`:** נבנה ב־Python מהשמות, ת״ז, המרכזיים, ההתחייבות והשולח. בלי ניקוד, עם איחוד של ״ ו־" ושל ׳ ו־', ובלי רווחים כפולים.
- **שאילתה:** `ILIKE '%…%'`, אחרי escape לתווים `%` ו־`_`. השאילתה עוברת את אותו נרמול.

### 2.6 התחברות והרשאות

| נושא | החלטה |
|---|---|
| משתמשים | נוצרים רק דרך `python -m scripts.create_user <username>`. הסיסמה נקלטת מ־prompt ולא מופיעה בהיסטוריה. אין הרשמה עצמית ואין תפקידים: כל משתמש מחובר יכול לתקן ולאשר |
| סיסמאות | `hashlib.scrypt` עם salt אקראי והשוואה ב־constant-time. מינימום 12 תווים |
| סשן | טוקן אקראי של 32 בתים. ב־DB נשמר רק ה־hash שלו. עוגייה `HttpOnly; Secure; SameSite=Strict; Path=/`. תפוגה אחרי 8 שעות של חוסר פעילות (החלטה D8) |
| CSRF | בבקשה שמשנה נתונים (POST, PATCH או DELETE), הכותרת `Origin` חייבת להיות הדומיין שלנו. ביחד עם `SameSite=Strict` |
| ניסיונות כניסה | 5 כישלונות נועלים את המשתמש ל־15 דקות. ההודעה כללית ולא מגלה אם המשתמש קיים |
| הרשאה | `require_user` רץ כ־dependency על כל router של `/api/v1`, כולל `extract` של A |
| ביקורת | `record_event` שומר מי עשה מה ומתי. בלוגים של השרת אין מידע אישי, רק מזהים וקודים |

### 2.7 אבטחה ופריסה

- **Docker:** בנייה רב־שלבית:
  1. `node:22` בונה את `frontend/dist`.
  2. `python:3.13-slim` מריץ את השרת עם משתמש שאינו root.
  3. FastAPI מגיש את `dist` עם fallback לנתיבי ה־SPA.

  כך ה־frontend וה־API יושבים באותו origin, ובפרודקשן אין CORS.
- **Render:** Web Service מסוג Docker עם deploy אוטומטי מ־`main`. הסודות (`DATABASE_URL`, `GEMINI_API_KEY`, `SESSION_SECRET` אם יידרש) נשמרים רק ב־Environment של Render.
- **Postgres של Render:** באותו אזור כמו השרת (Frankfurt). מסד חינמי אחד לכל workspace (החלטה D2).
- **כותרות אבטחה:**
  - `Content-Security-Policy: default-src 'self'; img-src 'self' blob: data:; frame-ancestors 'none'`
  - `Strict-Transport-Security`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: no-referrer`
  - `Cache-Control: no-store` על ה־API
- **בפרודקשן:** `/docs` ו־`/openapi.json` כבויים (`ENV=production`).
- **שמירה על השרת ער (`app/keep_alive.py`):** Render מרדים שרת חינמי אחרי 15 דקות בלי בקשות מבחוץ, והכניסה הבאה לוקחת בערך דקה.
  - **איך זה עובד:** משימת רקע (`asyncio`) מתחילה ב־lifespan של האפליקציה, ופונה כל 10 דקות לכתובת **הציבורית** של השרת עצמו: `GET {KEEP_ALIVE_URL}/api/health`. הבקשה יוצאת לאינטרנט וחוזרת דרך Render, ולכן היא נחשבת תנועה מבחוץ.
  - **מתי פעיל:** רק כש־`KEEP_ALIVE_URL` מוגדר, כלומר רק ב־Render. בפיתוח מקומי ובטסטים הוא כבוי. את המרווח קובעים ב־`KEEP_ALIVE_INTERVAL_S` (ברירת מחדל `600`).
  - **בלי תלות חדשה:** הפנייה נעשית עם `urllib.request` מהספרייה הסטנדרטית, בתוך `asyncio.to_thread`, עם timeout של 10 שניות.
  - **אמינות:** כישלון בפנייה נרשם כ־warning בלוג (רק קוד תשובה ומשך זמן) ולא עוצר את הלולאה. המשימה מבוטלת בצורה מסודרת כשהשרת יורד.
  - **מגבלה:** אם השרת נופל או מופעל מחדש, הלולאה מתחילה שוב כשהוא עולה. רק אם השרת כבר נרדם, אין מי שיעיר אותו עד הבקשה הבאה.
  - **מכסה:** שרת שער 24 שעות ביממה צורך בערך 744 שעות בחודש, מתוך 750 שעות חינמיות לכל workspace. לכן זה חייב להיות השרת החינמי היחיד ב־workspace.
- **פיתוח מקומי:** `docker compose up db` מרים Postgres 17, Vite מעביר את `/api` ל־8000, ולכן העוגייה עובדת באותו origin.
- **נתוני הדגמה:** רק קובצי הדוגמה של האתגר. `seed_demo.py` טוען אותם מחדש, ויש גם פקודת מחיקה.

---

## 3. Frontend

### 3.0 עיצוב: Claude Design קודם, React אחר כך

**מעצבים את הממשק ב־Claude Design (claude.ai/design) לפני שכותבים קוד React.** העיצוב הוא מקור האמת למראה: פריסה, צבעים, טיפוגרפיה ומצבים. הקוד בריפו נשאר React + TypeScript, עם הטסטים, ה־CI והחיבור ל־API, ובונים אותו לפי העיצוב.

| מה מעצבים | המצבים שחייבים להופיע |
|---|---|
| כניסה | רגיל, שגיאת סיסמה, נעילה זמנית (`429`) |
| העלאה ובדיקה | גרירת קבצים, התקדמות לפי קובץ, רשימת הרשומות של האצווה, עמוד שנכשל |
| עורך רשומה (עם תמונת העמוד לצידו) | שדה תקין, שדה דורש בדיקה (טקסט, אייקון וצבע), שדה ריק, שדה שתוקן, שדה שאושר ידנית, כפתור אישור חסום עם רשימת השדות, רשומה מאושרת, התנגשות גרסאות |
| רשומות | חיפוש, מסננים, מונים, טבלה, דפדוף, מצב ריק, טעינה |
| כללי | ניווט עליון, משתמש מחובר ויציאה, באנר שגיאת רשת, מסך "משהו השתבש" |

**כללים לעיצוב:**

- **שפה וכיוון:** עברית RTL מלאה.
- **סטטוסים:** כל סטטוס מוצג בטקסט ובאייקון, לא בצבע בלבד. הכתום משמש ל"דורש בדיקה", כמו בתסריט של האתגר.
- **נתונים:** רק נתונים מומצאים, לא שמות ומספרים מקובצי הדוגמה.
- **היקף:** העיצוב מכסה גם את הרכיבים של צפי (`UploadPanel`, `DocumentPreview`), כדי שהמסך ייראה אחיד. צפי מקבלת את הקישור (D16).

**המעבר לקוד:**

1. **tokens:** ה־tokens מהעיצוב (צבעים, גופנים, ריווח, רדיוסים) נכנסים ל־`shared/ui/tokens.css`. זה קובץ משותף, ולכן נכנס ב־PR משלו.
2. **רכיבים:** כל רכיב React נבנה לפי המסך המתאים בעיצוב.
3. **בדיקה מול העיצוב:** כל PR של ממשק כולל ב־"How I tested" צילום מסך לצד המסך המקביל בעיצוב.

### 3.1 מסכים

| מסך | נתיב | תוכן |
|---|---|---|
| כניסה | `/login` | טופס שם משתמש וסיסמה, הודעת שגיאה בעברית, פוקוס אוטומטי |
| העלאה ובדיקה | `/` | `UploadPanel` (A) מעלה קבצים. אחר כך מופיעה רשימת הרשומות של האצווה, ובחירה ברשומה פותחת עריכה עם `DocumentPreview` (A) לצידה. עמודים שנכשלו מוצגים עם הסיבה |
| רשומות | `/records` | חיפוש, מסננים, טבלה, דפדוף ומונים (ממתינות, מאושרות, דורשות בדיקה). המסננים נשמרים ב־query string, כך שרענון וכפתור "חזרה" לא מאבדים אותם |
| רשומה | `/records/:id` | אותם רכיבי בדיקה כמו במסך ההעלאה, תמונת העמוד, וכפתור אישור או תג "אושר על ידי X ב־…" |

### 3.2 רכיבים (מה ש־B בונה)

```
src/
├── App.tsx                         # Router, AuthProvider, Layout עם ניווט ויציאה, ErrorBoundary
├── api/client.ts                   # fetch עם טיפוסים מ-schema.d.ts, ApiError, טיפול ב-401
├── features/auth/                  # AuthProvider, useAuth, LoginPage, RequireAuth
├── features/review/
│   ├── RecordEditor.tsx            # 6 שדות + רשימת מרכזיים + התחייבות + issues
│   ├── FieldCell.tsx               # הצגה, עריכה, "אישור ערך" (confirmed), raw מול value
│   ├── CentralNumbersEditor.tsx    # הוספה והסרה של פריטים
│   ├── SenderSelect.tsx            # רשימה סגורה מ-/senders, עם אפשרות להשאיר טקסט לא מוכר מסומן
│   ├── ApproveButton.tsx           # מושבת + רשימת השדות שחוסמים; טיפול ב-409
│   ├── BatchRecordsList.tsx        # הרשומות של ההעלאה הנוכחית
│   ├── reviewReducer.ts            # טיוטת עריכה מקומית לרשומה (קיים כשלד)
│   └── useRecordMutations.ts       # patch, approve, delete, כולל version
├── features/records/
│   ├── RecordsPage.tsx, RecordsFilters.tsx, RecordsTable.tsx, Pagination.tsx
│   ├── useRecordsQuery.ts          # שאילתה מ-query string, debounce של 300ms לחיפוש
│   └── RecordPage.tsx
├── shared/ui/StatusBadge.tsx       # טקסט + אייקון, לא צבע בלבד
└── features/export/, review/useValidate.ts → נמחקים
```

### 3.3 ניהול state

- **בלי Redux** (החלטה קיימת), ובלי ספריית state חיצונית.
- **מצב שרת:** hooks לכל מסך (`useRecordsQuery`, `useRecord`) עם `useState` ו־`useEffect`, ו־`AbortController` לביטול בקשות ישנות.
  - **אחרי PATCH:** הרשומה שחוזרת מהשרת מחליפה את המקומית. השרת הוא מקור האמת לסטטוסים.
- **טיוטת עריכה:** `reviewReducer` מחזיק את הערכים שהוקלדו ועוד לא נשלחו. השמירה נשלחת ביציאה מהשדה (blur) או ב־Enter.
- **התחברות:** `AuthProvider` טוען את `/auth/me` פעם אחת בעליית האפליקציה ומחזיק את `user`. אם התשובה `401`, הנתיבים המוגנים מפנים ל־`/login`.
- **מסננים:** נשמרים ב־URL ולא ב־state, כדי שאפשר יהיה לשתף קישור ולחזור לאותה תצוגה.

### 3.4 חיבור ל־API

- **טיפוסים:** נוצרים מ־`openapi.json` (`npm run gen:api`). אין כתיבה ידנית של טיפוסי החוזה.
- **`client.ts`:**
  - כל הקריאות נשלחות עם `credentials: 'same-origin'`, וכתובת הבסיס היא `VITE_API_BASE_URL` (ריק כברירת מחדל).
  - תשובה עם `problem+json` הופכת ל־`ApiError {status, type, title, detail, fields?}`.
  - `401` מפעיל `onUnauthorized` שמפנה לכניסה.
- **תמונת העמוד:** `<img src="/api/v1/pages/{id}/image">`. העוגייה נשלחת אוטומטית.

### 3.5 טיפול בשגיאות (כל ההודעות בעברית: מה קרה ומה לעשות)

| מצב | התנהגות |
|---|---|
| `401` | מעבר לכניסה, ואחרי הכניסה חזרה לאותו מסך |
| `409 version_conflict` | "הרשומה עודכנה בחלון אחר", טעינה מחדש של הרשומה, והטיוטה נשמרת להשוואה |
| `409 review_required` | הדגשת השדות מ־`blocking_fields` וקפיצה לראשון שבהם |
| `409 record_approved` / `sibling_approved` | הודעה שמסבירה למה אי אפשר לערוך |
| `422` | הודעה ליד השדה |
| `429` בכניסה | "יותר מדי ניסיונות, נסי שוב בעוד 15 דקות" |
| שגיאת רשת או `5xx` | באנר עם "נסי שוב". הטיוטה לא נמחקת |
| שגיאה לא צפויה ברינדור | `ErrorBoundary` מציג מסך "משהו השתבש" עם כפתור רענון |

**נגישות:** RTL עם CSS logical properties. כל פעולה זמינה מהמקלדת, הפוקוס נראה, וכל סטטוס מוצג גם בטקסט וגם באייקון.

---

## 4. סדר עבודה ותלויות

```
B0.1 ─┐
B0.2 (חוזה) ──────────────┬─► B1.5 (API) ─► B2.1 (אינטגרציה) ─► B2.2 ─► B3
B0.3 (Postgres) ─► B1.2 ─► B1.3 ─┘   ▲                ▲
B0.4 (פריסה ראשונה) ───────────────────┼────────────────┘
B1.1 (כללים, מתחילים מיד) ─► B1.3     │
B1.4 (auth) ─► B1.5                    │
B0.2 + B0.5 (עיצוב ב-Claude Design) ─► B1.6 (FE בסיס) ─► B1.7, B1.8 ──┘
B2.3 (מדידה) אחרי B2.1, במקביל ל-B2.2
```

**תנאי סיום לכל משימה, בנוסף ל־DoD שלה בטבלה:**

- **טסטים:** הטסטים שמפורטים בסעיף 7 נוספו ועוברים.
- **PR:** המשימה עלתה מענף משלה, ב־commits קטנים, ב־PR עם תיאור באנגלית (סעיף 8).
- **מיזוג:** ה־PR מוזג אחרי ש־CI ירוק (`backend`, `frontend`, `contract`).

**מה רץ במקביל:**

- **מיד:** B1.1 (כללים) לא תלויה בכלום ומתחילה מיד, במקביל ל־B0.2 ול־B0.3.
- **אחרי החוזה:** ה־frontend (B1.6 עד B1.8) מתחיל ברגע שהחוזה מוזג ו־`schema.d.ts` קיים. עד שה־API מוכן עובדים עם נתוני דמה מה־fixtures.

### 4.1 משימות

**יום א׳ 18.10: יסודות**

| # | משימה | תוצר | Definition of Done | תלוי ב |
|---|---|---|---|---|
| B0.1 | ~~סגירת PR #3~~ (מוזג). נשאר: PR לענף `chore/ground-truth-per-commitment` (עמודת `commitment_number`, ו־`.claude/` ב־`.gitignore`) | PR ממוזג | CI ירוק, ו־`main` כולל את הכותרת המעודכנת | — |
| B0.0 | **לקבל מצפי תשובות ל־A1–A9, בעיקר A1, A2, A8 ו־A9** (סעיף 5.1א), ובאותה הודעה גם D10 ו־D11 | תשובה בכתב (תגובה ב־PR או הודעה), שמתועדת ב־GUIDELINES §9 | כל שורה ב־5.1א מסומנת "אושר" או "שונה ל־…". מה ששונה מעודכן בתוכנית הזו | — |
| B0.2 | השלמת החוזה (הטיוטה מ־PR #4 כבר מוזגה): מה שנשאר לפי 2.3, מחיקת `export`/`validate`/`ExportButton`/`useValidate`, SPEC 0.3 לפי GUIDELINES §6, ועדכון CODEOWNERS (בלי חובת אישור) | `schemas/api.py`, `openapi.json`, `schema.d.ts`, `docs/SPEC.md` | בדיקת `contract` ירוקה, צפי מיזגה, ו־`/docs` מציג את כל ה־endpoints מסעיף 2.2 | B0.0 (A1, A8, A9). אפשר לפתוח טיוטה לפני התשובה |
| B0.3 | מעבר ל־Postgres: `docker-compose.yml` (db), `schema.sql` ו־`db.py` לפי 2.4, `DATABASE_URL` ב־`settings.py` וב־`.env.example`, כתיבה מחדש של `test_db.py`, ו־service של Postgres ב־job `backend` ב־`ci.yml` | שכבת DB עובדת מקומית וב־CI | `pytest` ירוק מקומית וב־CI מול Postgres אמיתי. אפס מוביל נשמר. השרת מסרב לעלות על גרסת סכמה שגויה ומסביר מה לעשות | הקבצים שלי: בלי תלות. `settings.py` ו־`ci.yml`: A8 ⏳ ו־D11 ⏳ |
| B0.4 | פריסה ראשונה: Dockerfile, `.dockerignore`, הגשת `dist` מ־FastAPI, Render עם Postgres מנוהל, משתני סביבה, keep-alive (2.7) | URL ציבורי עם HTTPS | `https://<domain>/api/health` מחזיר ok. דף הבית נטען. deploy אוטומטי ממיזוג ל־`main` עובד. `docker build` עובר מקומית. בלוגים של Render יש פנייה עצמית כל 10 דקות | B0.3 (לחיבור ל־DB) |
| B0.5 | **עיצוב הממשק ב־Claude Design** (סעיף 3.0): 4 המסכים וכל המצבים שלהם, ב־RTL ועם נתונים מומצאים. מוגבל ל־2–3 שעות | פרויקט Design ב־Claude Design (קישור), ורשימת tokens | את מאשרת את העיצוב, וצפי ראתה את החלקים שלה (`UploadPanel`, `DocumentPreview`). כל מצב מטבלה 3.0 מופיע בעיצוב. ה־tokens (צבעים, טיפוגרפיה, ריווח) רשומים | — (במקביל ל־backend) |
| B1.1 | כללים: `normalize`, `validators`, `review_policy`, `engine.apply_rules`, `rules/records.build_records`, ו־`senders.yaml` עם הרשימה הסגורה והכינויים | מודולים טהורים ובדיקות | כל קוד issue מ־SPEC 8 נבדק. ארבעת ה־fixtures עוברים. 2 התחייבויות ו־3 מרכזיים נותנים 2 רשומות. `apply_rules(apply_rules(f)) == apply_rules(f)` | — |

**יום ב׳ 19.10: ליבה**

| # | משימה | תוצר | Definition of Done | תלוי ב |
|---|---|---|---|---|
| B1.2 | `repo.py`: `save_page`, `list_records` (q ומסננים, דפדוף, מונים), `get_record`, `update_fields` עם version, `set_approved`, `delete_pending`, `get_page_image`, `find_by_commitment` | כל ה־SQL בקובץ אחד | בדיקות מול Postgres: חיפוש עם גרשיים, כל מסנן לבד ובשילוב, `409` על גרסה ישנה, מחיקה ב־cascade, ואין SQL מחוץ ל־`repo.py` | B0.3, B0.2 |
| B1.3 | `storage/service.py`: `save_extracted_page`, `patch_record` (כולל אחיות ו־`DUPLICATE_RECORD`), `approve_record`, ורישום ב־`record_event` | שכבת לוגיקה מעל ה־repo | בדיקות: אישור נחסם עם שדה מסומן ועובר אחרי תיקון או `confirmed`. תיקון ת״ז מתעדכן באחיות. התחייבות כפולה מסומנת. עמוד שנשמר הוא טרנזקציה אחת (כשל באמצע לא משאיר שאריות) | B1.1, B1.2 |
| B1.4 | התחברות: הטבלאות `users` ו־`sessions`, `auth/*`, `api/auth.py`, `scripts/create_user.py`, נעילה אחרי ניסיונות | כניסה, יציאה, `me`, `require_user` | בדיקות: סיסמה שגויה מחזירה `401` עם הודעה כללית. בכישלון השישי מקבלים `429`. העוגייה עם `HttpOnly`/`Secure`/`SameSite`. כל `/api/v1/*` בלי סשן מחזיר `401`. אחרי logout הטוקן לא עובד. Origin זר מחזיר `403` | B0.3 |
| B1.5 | `api/records.py` (records, pages, senders) וחיבור ב־`main.py`: routers, lifespan עם init_db ו־pool, ו־`require_user` | API מלא | בדיקות `TestClient` לכל endpoint, כולל `401`/`404`/`409`/`422`. `export_openapi --check` ירוק | B1.3, B1.4 |
| B1.6 | בסיס FE: `client.ts` ו־`ApiError`, `AuthProvider`, `LoginPage`, `RequireAuth`, `App.tsx` עם ניווט ו־`ErrorBoundary` | שלד אפליקציה עם כניסה | כניסה, רענון ויציאה עובדים מול השרת המקומי. נתיב מוגן בלי סשן מפנה לכניסה. `lint`, `build` ו־`test` ירוקים | B0.2, B0.5 (ו־B1.4 לבדיקה מלאה) |
| B1.7 | מסך בדיקה: `RecordEditor`, `FieldCell`, `CentralNumbersEditor`, `SenderSelect`, `ApproveButton`, `BatchRecordsList`, `useRecordMutations`, ו־`DocumentPreview` מ־URL (בתיאום עם A) | תיקון ואישור על המסך | תיקון בשדה מעדכן את הסימון מתשובת השרת. "אישור ערך" מסיר את הסימון וה־issue נשאר מוצג. כפתור האישור מושבת עם רשימת השדות החוסמים. `409` מטופל. vitest ל־reducer ולוגיקת החסימה | B1.6, B1.5 |
| B1.8 | מסך רשומות ודף רשומה: חיפוש, מסננים (סטטוס, דורש בדיקה, שולח, טווח תאריכים), טבלה, דפדוף, מונים, סנכרון URL | חזרה לרשומות | כל מסנן משנה את התוצאות. חיפוש לפי חלק מת״ז או ממרכזי מוצא את הרשומה. מצב ריק מוסבר. תאריכים מוצגים כ־`DD/MM/YYYY`. רענון שומר את המסננים | B1.6, B1.5 |

**יום ג׳ 20.10: אינטגרציה, אבטחה, מדידה. הקפאה בערב.**

| # | משימה | תוצר | Definition of Done | תלוי ב |
|---|---|---|---|---|
| B2.1 | אינטגרציה עם A: `extract` קורא ל־`save_extracted_page`. התרחיש המלא על קובצי הדוגמה **בדומיין החי** | מסלול מקצה לקצה | העלאת PDF ותמונה, ואז רשומות על המסך, תיקון, אישור, ואז הרשומה "מאושרת" במסך הרשומות. היא נשארת שם גם אחרי יציאה וכניסה. עמוד שנכשל מוצג ולא נשמר | B1.5, B1.7, B1.8, A (A2 ⏳: מי כותבת את הקריאה) |
| B2.2 | הקשחה: `security.py` עם הכותרות, `/docs` כבוי בפרודקשן, בדיקה שאין מידע אישי בלוגים, `seed_demo.py` ופקודת מחיקה, משתמש הדגמה לשופטים | רשימת בדיקת אבטחה ב־README | `curl -I` מראה את כל הכותרות. `/docs` בפרודקשן מחזיר `404`. הלוגים של Render נקיים מת״ז ושמות. משתמש ההדגמה עובד | B0.4, B2.1 |
| B2.3 | מדידה: `run_eval.py` מול `ground_truth.csv` (10–15 טפסים, ממלאות יחד). מדדים: דיוק לפי שדה, כיסוי, **שגיאות שלא סומנו**, מספר רשומות מול הצפוי, אפסים מובילים, זמן לעמוד. רץ על הפלט אחרי הכללים ולפני תיקון אנושי, עם `CachedProvider` כדי לא לבזבז מכסה | דוח Markdown עם מספרים אמיתיים | הדוח רץ מפקודה אחת, והתוצאות נכנסות ל־README בלי עיגול לטובה | B1.1, B1.3, A (cache) |
| B2.4 | הקפאה: רק תיקוני באגים. עדכון PLAN.md | גרסה מועמדת | הרצה נקייה בדומיין עוברת | הכול |

**יום ד׳ 21.10: הגשה**

| # | משימה | תוצר | Definition of Done |
|---|---|---|---|
| B3.1 | תיעוד: README (כתובת חיה, איך מקבלים פרטי כניסה, הרצה מקומית ב־docker compose, משתני סביבה, אבטחה, מגבלות, תוצאות המדידה), SPEC 0.3 סופי, PLAN | מסמכים מעודכנים | מישהי שלא מכירה את הפרויקט מרימה אותו מקומית לפי ה־README בלבד |
| B3.2 | smoke בדומיין: עמוד רגיל ועמוד קשה. תוכנית גיבוי: `docker compose up` מקומי אם Render נופל | הגשה | ההגשה נשלחה לפני שעת הסגירה, ושתינו מחזיקות עותק עובד |

### 4.2 על מה מוותרים אם אין זמן (לפי הסדר)

1. `DELETE` לרשומה
2. מיון לפי עמודות במסך הרשומות
3. `DUPLICATE_RECORD`
4. `seed_demo.py` (טוענים ידנית)

**לא מוותרים על:** התחברות, אישור חסום בשרת, חיפוש וסינון, ממתין מול מאושר, דומיין חי, מדידה.

---

## 5. סיכונים והחלטות פתוחות

### 5.1א ממתין לצפי: A1–A9

צפי עוד לא ענתה. התוכנית בנויה לפי ההצעה בכל שורה. אם היא משנה תשובה, העמודה האחרונה מראה מה צריך לעבוד מחדש.

| # | השאלה | מה התוכנית מניחה (ההצעה) | חוסם את | אם צפי משנה |
|---|---|---|---|---|
| A1 | חוזה `Record`, `records` במקום `forms`, בלי `preview_image` | כמו שהוצע. **הטיוטה כבר מוזגה (PR #4)** | B0.2 ואחריה כל ה־FE וה־API | עדכון `schemas/api.py` והטיפוסים. הכללים ושכבת ה־DB לא משתנים |
| A2 | מי כותבת את הקריאה לשמירה בסוף `extract` | A קוראת ל־`save_extracted_page`, ו־B מספקת אותה ואת הבדיקות | B2.1 | B כותבת את הקריאה בקובץ של A, באישורה |
| A3 | תיקון שדה משותף מתעדכן ברשומות האחיות | כן, חוץ מ־`commitment_number` | B1.3 | מוחקים את העדכון ברשומות האחיות. פחות קוד |
| A4 | התחייבות כפולה | לא חוסמים, `DUPLICATE_RECORD` (warning) | B1.3 | ממילא ברשימת הוויתורים (4.2) |
| A5 | מחיקת רשומה | כן, רק כשהיא ממתינה | B1.5 | מוותרים על `DELETE`. ממילא ראשון ברשימת הוויתורים |
| A6 | ביטול אישור | לא | B1.3, D5, D6 | endpoint `unapprove` ומחיקת `409 record_approved`: בערך חצי יום |
| A7 | עמוד שנכשל לא נשמר | לא שומרים, מחזירים ב־`failed_pages` | B1.3, B2.1 | טבלה או סטטוס לעמודים שנכשלו |
| A8 | שינויים בקבצים של A (`main.py`, `settings.py`, `extract.py`/`service.py`, `client.ts`, `DocumentPreview.tsx`, `App.tsx`) | מאושר | B0.3, B1.5, B1.6, B1.7 | בלי אישור B לא נוגעת בקבצים האלה, ו־A מבצעת את השינויים לפי מפרט מ־B |
| A9 | ויתור על ייצוא לקובץ | כן | B0.2 (מחיקת `export`) | ייצוא CSV מ־`GET /records?status=approved`: בערך חצי יום, אחרי ההקפאה רק אם יש זמן |

**מה לא מחכה לצפי:** B1.1 (כללים), B1.4 (התחברות), ה־DB בקבצים שלי, B0.4 (Dockerfile), וטיוטה של B0.2.

### 5.1 החלטות שצריכות אישור (שלך, ושל צפי כשמסומן)

| # | החלטה | ההמלצה | למה |
|---|---|---|---|
| D1 | תלויות חדשות ב־backend | `psycopg[binary,pool]` בלבד. סיסמאות עם `hashlib.scrypt` מהספרייה הסטנדרטית, בלי bcrypt או argon2 | מינימום תלויות |
| D2 | איפה Postgres | **Postgres של Render** (חינמי, Frankfurt) | הכול בפלטפורמה אחת: לוח בקרה אחד, רשת פנימית, ובלי חשבון נוסף. המגבלות: המסד החינמי פג 30 יום אחרי שנוצר. אם ייווצר ב־18–19.10, הוא יפוג בערך ב־17.11, אחרי ערב הגמר ב־28.10. אחרי שהוא פג יש 14 יום לשדרג לתוכנית בתשלום, ואחרי זה הוא נמחק. בנוסף: נפח של 1GB ואין גיבויים. החלופה היא Neon, שלא פג, אבל זה חשבון נוסף |
| D3 | Render חינמי או בתשלום | ✅ **הוחלט:** חינמי, עם keep-alive בתוך האפליקציה כל 10 דקות (2.7). Starter (בערך 7$ לחודש) נשאר גיבוי, אם יתברר שהשרת בכל זאת נרדם | בגרסה החינמית השרת נרדם אחרי 15 דקות, והכניסה הראשונה לוקחת בערך דקה, מול השופטים |
| D4 | דומיין | `*.onrender.com` מספיק, או דומיין משלנו? | צריך לברר אם זה עונה על "דומיין חי" |
| D5 | תיקון שדה משותף כשרשומה אחות כבר אושרה | `409 sibling_approved`: חוסמים ומסבירים | תלוי ב־A3 ו־A6 ⏳: בלי ביטול אישור, אסור לשנות בשקט רשומה מאושרת |
| D6 | עריכה של רשומה מאושרת | חסומה (`409 record_approved`) | נגזר מ־A6 ⏳ |
| D7 | ספריית ניתוב ב־frontend | `react-router` (תלות אחת) | נתיב `/records/:id` לחזרה לרשומה. החלופה היא router ידני של כ־40 שורות |
| D8 | מדיניות סשן ונעילה | 8 שעות של חוסר פעילות. 5 ניסיונות נועלים ל־15 דקות | |
| D9 | משתמשים לדמו | 3 משתמשים: B, A ו־`judge-demo`. פרטי השופטים נמסרים בטופס ההגשה, לא ב־README | ה־README ציבורי |
| D10 | שינויים בקבצים של A מעבר לרשימת A8 (**צפי**) | `main.py`: middleware אבטחה והגשת `dist`. `extract` מאחורי `require_user` | A8 כיסה רק routers, init ו־DB |
| D11 | שינוי ב־`ci.yml` (**צפי**, קובץ משותף) | service של Postgres ב־job `backend` בלי לשנות את שמות ה־jobs. אופציונלי: job של `docker build` | שמות ה־jobs הם הבדיקות החובה בהגנה על `main` |
| D12 | עדכון הניסוח על פרטיות | SPEC 11.1, README ו־GUIDELINES §2.1: הנתונים נשמרים ב־Postgres מנוהל ב־EU, רק דוגמאות האתגר, ומחיקה בפקודה אחת | הנימוק הקודם ל־SQLite ("המידע לא יוצא מהמחשב") כבר לא נכון |
| D13 | יומן ביקורת | כותבות ל־`record_event` בלי מסך להצגה | ההצגה היא NICE TO HAVE |
| D14 | תבנית ה־PR (**צפי**, קובץ משותף) | לתרגם את `.github/pull_request_template.md` לאנגלית, באותם סעיפים ואותו צ׳קליסט, ב־PR קטן משלו | תיאורי ה־PR נכתבים באנגלית, והתבנית היום בעברית |
| D16 | העיצוב ב־Claude Design מכסה גם את הרכיבים של צפי (**צפי**) | כן: עיצוב אחד לכל האפליקציה. צפי מקבלת את הקישור ומאשרת את `UploadPanel` ו־`DocumentPreview` | בלי זה המסך ייראה כמו שני מוצרים שונים |
| D15 | תלויות פיתוח ב־frontend לטסטים של רכיבים | `@testing-library/react`, `@testing-library/user-event`, `jsdom` (devDependencies בלבד) | בלעדיהן אפשר לבדוק רק פונקציות טהורות, לא רכיבים |

### 5.2 סיכונים

| סיכון | סבירות | מה עושים |
|---|---|---|
| זמן: 3 ימים לכל ההיקף | גבוהה | הסדר בסעיף 4, רשימת הוויתורים ב־4.1, ופריסה כבר ביום הראשון (B0.4) כדי לא לגלות בעיות פריסה ביום ההגשה |
| הסבת SQLite ל־Postgres שוברת את הבדיקות הקיימות | בינונית | B0.3 ראשונה. בדיקות מול Postgres אמיתי, גם ב־CI |
| עוגיות בפיתוח מקומי (שני פורטים) | בינונית | proxy של Vite כך שהכול באותו origin, ובפרודקשן אותו שרת. `Secure` מושבת רק כש־`ENV=development` |
| צפי לא עונה על A1–A9 בזמן, או משנה תשובה אחרי שהעבודה התחילה | בינונית | לשלוח לה היום עם בקשה לענות קודם על A1, A8 ו־A9 (הן חוסמות). להתחיל במה שלא תלוי בה (5.1א). עלות השינוי לכל תשובה מפורטת ב־5.1א |
| PR החוזה מתעכב וחוסם את A ואת ה־FE | בינונית | לפתוח אותו ראשון היום. ה־FE עובד מול fixtures עד המיזוג |
| מכסת Gemini או חיוב (באחריות A) חוסמים את האינטגרציה והמדידה | גבוהה | `FakeProvider` לאינטגרציה, `CachedProvider` למדידה |
| השרת רדום מול השופטים | נמוכה, עם keep-alive | `keep_alive.py` (2.7). ב־B3.2 ולפני 28.10: לוודא בלוגים של Render שיש פנייה כל 10 דקות, ושהאתר עונה מיד אחרי חצי שעה בלי שימוש. אם לא, לעבור ל־Starter (D3) |
| חריגה מ־750 השעות החינמיות של Render | נמוכה | לוודא שאין שרת חינמי נוסף באותו workspace, כולל שרתים של צפי |
| המסד החינמי של Render פג, או מושבת לתחזוקה | פג: ודאי, בערך ב־17.11. תחזוקה: נמוכה | ליצור את המסד רק כשמתחילות את B0.4, לא קודם. `seed_demo.py` בונה מחדש את נתוני ההדגמה תוך דקות. אם צריך את הדמו גם אחרי נובמבר, לשדרג אותו |
| העיצוב ב־Claude Design לוקח יותר זמן מהמתוכנן | בינונית | מוגבל ל־2–3 שעות (B0.5). ה־backend ממשיך במקביל. אם הזמן נגמר, מתחילות לקודד לפי מה שכבר עוצב, ומשלימות את השאר תוך כדי |
| CSP חוסם משאב של Vite | נמוכה | בדיקה על ה־build בפרודקשן (B2.2) לפני ההקפאה |
| מידע אישי בלוגים או ב־Git | נמוכה | אין לוג של גוף בקשה. `.env` ו־PDF ב־`.gitignore`. בדיקה ב־B2.2 |

---

## 6. איך בודקים שהכול עובד

**בדיקות אוטומטיות (לפני כל PR, וב־CI):**

```powershell
# backend/
docker compose up -d db
.\.venv\Scripts\python.exe -m ruff check . ; .\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.export_openapi --check
# frontend/
npm run lint ; npm run build ; npm test
```

**הרצה מקומית מלאה:**

1. `docker compose up` (db)
2. `python -m scripts.create_user dev`
3. מריצים את השרת עם `uvicorn`, ואת הממשק עם `npm run dev`.

**בדיקת קבלה ידנית בדומיין החי** (אחרי B2.1, ושוב ביום ההגשה):

1. כניסה עם משתמש ההדגמה. בלי כניסה, `/records` מפנה למסך הכניסה.
2. העלאה של PDF חלק 1 (חלק מהעמודים) ושל צילום אחד. מופיעות רשומות, ועמוד עם 3 התחייבויות נותן 3 רשומות עם אותם מרכזיים.
3. שדה מסומן: תיקון, והסימון מתעדכן. ניסיון לאשר עם שדה מסומן נחסם, ומופיעה רשימת השדות.
4. "אישור ערך" על שדה ריק בטופס בלי התחייבות, ואז אישור הרשומה עובר.
5. במסך הרשומות: חיפוש לפי חלק מהמרכזי, וסינון "ממתין" מול "מאושר". הרשומה שאושרה מופיעה כמאושרת.
6. יציאה וכניסה מחדש: הרשומות עדיין שם, ותמונת העמוד נטענת.
7. עריכה של אותה רשומה בשני חלונות. השני מקבל הודעת התנגשות.
8. `curl -I https://<domain>/` מחזיר את כותרות האבטחה, ו־`/docs` מחזיר `404`.
9. keep-alive: בלוגים של Render מופיעה פנייה ל־`/api/health` כל 10 דקות. אחרי חצי שעה בלי שימוש, האתר נטען מיד ולא אחרי דקה.

---

## 7. בדיקות (טסטים)

### 7.1 עקרונות

- **בכל PR:** כל PR מוסיף טסטים להתנהגות שהוא מוסיף. תיקון באג מתחיל בטסט שנכשל, ורק אחר כך בא התיקון.
- **אין נתונים אמיתיים:** בטסטים ובפיקסצ׳רים יש רק נתונים מומצאים. ת״ז סינתטיות עם ספרת ביקורת תקינה, למשל `000000018` ו־`011223344`. אין שמות או מספרים מקובצי הדוגמה.
- **Postgres אמיתי:** ה־DB לא מדומה. טסטים של `repo`, `service` ו־API רצים מול Postgres (מקומית ב־`docker compose`, וב־CI כ־service), כי הם בודקים דברים שקיימים רק ב־DB אמיתי: SQL, טרנזקציות, CHECK ו־cascade.
- **בלי תלויות בדיקה חדשות ב־backend:** אין `freezegun` ואין `pytest-cov`. זמן נבדק דרך שעון שמוזרק (`now` כפרמטר).
- **בלי E2E אוטומטי:** אין Playwright, בגלל הזמן. במקומו יש רשימת בדיקה ידנית (סעיף 6), שמריצים בדומיין לפני ההקפאה וביום ההגשה.

### 7.2 שכבות

| שכבה | איפה | כלי | מה נבדק |
|---|---|---|---|
| כללים (טהור) | `backend/tests/unit/rules/` | pytest, `parametrize` | כל שורה בטבלאות SPEC 5.2–5.6 ו־SPEC 8. idempotency. `raw` לא משתנה. `issues` שמגיעים מהלקוח לא נלקחים בחשבון |
| שמירה | `backend/tests/unit/storage/` | pytest + Postgres | סכמה, `repo`, `service`, טרנזקציות, גרסאות, חיפוש וסינון |
| התחברות | `backend/tests/unit/auth/` | pytest + Postgres | גיבוב, סשנים, נעילה, CSRF, דגלי העוגייה |
| API | `backend/tests/unit/api/` | `TestClient` + Postgres | כל endpoint: הצלחה, `401`, `404`, `409`, `422`, וגוף ה־problem |
| חוזה | `backend/tests/contract/` | pytest + CI `contract` | JSON לדוגמה עובר את המודלים. `openapi.json` ו־`schema.d.ts` מעודכנים |
| Frontend | ליד הקוד, `*.test.ts(x)` | vitest (+ testing-library, D15) | reducer, client, מיפוי URL למסננים, רכיבים קריטיים |
| ידני | סעיף 6 | דפדפן, `curl` | התרחיש המלא בדומיין החי |

### 7.3 fixtures משותפים (`backend/tests/conftest.py`)

- **`db`:** מתחבר ל־`TEST_DATABASE_URL`, יוצר את הסכמה פעם אחת לכל ריצה, ומריץ `TRUNCATE … CASCADE` לפני כל טסט. אם ה־DB לא זמין, הטסט נכשל עם הודעה ברורה ("הריצי `docker compose up -d db`") ולא מדלג בשקט.
- **`make_form(**overrides)`:** בונה טופס כמו ש־`assemble.py` מחזיר, על בסיס ה־fixtures ב־`tests/fixtures/rules/`.
- **`user`, `client`, `auth_client`:** משתמש בדיקה, לקוח אנונימי, ולקוח עם סשן ו־`Origin` תקין.
- **`expected/*.json`:** הפלט הצפוי של `apply_rules` לכל אחד מארבעת ה־fixtures (golden files). שינוי מכוון בכללים מעדכן אותם באותו commit.

---

## 8. ענפים, commits ו־PRs

### 8.1 כללים

**ענפים:**

- כל משימה (או חלק ממשימה) בענף משלה, שנפתח מ־`main` מעודכן:

  ```
  git switch main ; git pull ; git switch -c <type>/<name>
  ```

- סוגי ענפים: `feature/` ליכולת חדשה, `chore/` לתשתית, CI ותלויות, `fix/` לתיקון באג, `docs/` לתיעוד בלבד. השם ב־kebab-case.
- **לפני כל push** בודקים שה־PR של הענף לא כבר מוזג. צפי ממזגת מהר, וזה כבר קרה פעם. אם הוא מוזג, ממשיכים בענף חדש מ־`main`.

**commits:**

- קטנים, ושינוי לוגי אחד בכל commit. כל commit עובר `ruff` וטסטים בעצמו.
- כותרת באנגלית, בציווי, באות גדולה, עד 72 תווים, בלי נקודה ובלי prefix, כמו בהיסטוריה הקיימת (`Add ruff lint and format check, pin Python 3.13`).
- גוף ההודעה (כשצריך) מסביר **למה** ומה כדאי לדעת, בשורות של עד 72 תווים.
- הטסט נכנס באותו commit עם הקוד שהוא בודק.
- שינוי ב־`schemas/api.py` נכנס באותו commit עם `openapi.json` ו־`schema.d.ts` שנוצרו ממנו (כפי שדורש הצ׳קליסט בתבנית).
- commit ש־Claude כותבת מסתיים ב־`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, כמו בהיסטוריה.
- **אף פעם לא נכנסים:** `.env`, PDF, קבצי DB, נתונים אמיתיים, `node_modules`, `dist`.

**PRs:**

- PR אחד לכל שורה בטבלה 8.2. היעד: עד בערך 400 שורות שינוי, בלי לספור קבצים שנוצרו אוטומטית ו־lock files.
- כותרת באנגלית, בציווי.
- תיאור באנגלית לפי התבנית (D14):

  ```
  ## What and why
  1–3 lines. Refs: Dev-B plan B1.3, SPEC §7.4

  ## How I tested
  - pytest tests/unit/storage/test_service.py (9 new tests)
  - Manual: <steps>, screenshot for UI changes

  ## Checklist
  (the template checklist: own files only, contract regenerated, no PII, no secrets, PLAN.md updated)

  ## Notes
  Open questions / what is intentionally left out
  ```

- **מיזוג:** CI ירוק בלבד, בלי חובת אישור. PR שנוגע בקבצים של צפי או בקבצים משותפים מתייג אותה בתיאור, וממתינים ל־OK שלה בתגובה. זה הסכם בינינו, לא חסימה ב־GitHub. משאירות merge commit (כמו היום), כדי שה־commits הקטנים יישארו בהיסטוריה.

### 8.2 פירוק ל־PRs

| PR | משימה | ענף | כותרת | commits מתוכננים | טסטים |
|---|---|---|---|---|---|
| 1 | B0.1 | `chore/ground-truth-per-commitment` (כבר ב־push) | Use one ground truth row per commitment | *(קיימים)* `Use one ground truth row per commitment number` · `Ignore local Claude Code settings` | — (כותרת CSV בלבד) |
| 2 | D14 | `chore/pr-template-english` | Translate PR template to English | `Translate pull request template to English` | — |
| 3 | B0.2 | `feature/complete-records-contract` | Complete records contract and remove Excel export | `Remove Excel export modules and endpoints` · `Remove export button and validate hook from frontend` · `Add auth models to the contract` · `Add approved_by, updated_by and list counts` · `Add delete record and senders endpoints` | `tests/contract/test_records_schema.py`: Record לדוגמה עובר. המזהים מחרוזות. `commitment_number` בודד. אין `preview_image`. CI `contract` ירוק |
| 4 | B0.2 | `docs/spec-v0.3` | Update SPEC to v0.3 for records | `Update SPEC sections 0–4 for records` · `Update SPEC sections 7–13 for records, auth and Postgres` | — |
| 5 | B0.3 | `chore/postgres-storage` | Move storage from SQLite to Postgres | `Add docker compose with Postgres for local development` · `Add psycopg and DATABASE_URL setting` · `Port records schema to Postgres` · `Replace SQLite connection with psycopg pool` · `Add Postgres test fixtures` · `Run backend tests against Postgres in CI` | `test_db.py`: init יוצר טבלאות, init שני לא משנה כלום, גרסה שגויה נכשלת עם הודעה, אפס מוביל נשמר, cascade מעמוד לשדות, `CHECK` על status |
| 6 | B0.4 | `chore/docker-render-deploy` | Serve the app from one Docker image on Render | `Add multi-stage Dockerfile and dockerignore` · `Serve built frontend from FastAPI with SPA fallback` · `Add Render blueprint for web service and database` · `Document deployment and environment variables` | `test_spa.py`: `/records/x` מחזיר `index.html`, `/api/nope` מחזיר `404` JSON ולא HTML, קובץ סטטי מוגש. `docker build` מקומי. ידני: `/api/health` בדומיין |
| 6א | B0.4 | `feature/keep-alive` | Keep the free Render instance awake | `Add keep-alive loop that pings the public health URL` · `Start keep-alive from app lifespan in production only` (main.py, A8 ⏳) · `Document KEEP_ALIVE_URL and interval` | `test_keep_alive.py`: עם פונקציית ping מדומה ומרווח קצר, ה־ping נקרא כמה פעמים. חריגה ב־ping לא עוצרת את הלולאה. כש־`KEEP_ALIVE_URL` ריק, לא נוצרת משימה. המשימה מבוטלת ב־shutdown. ידני: בלוגים של Render יש `200` כל 10 דקות |
| 7 | B1.1 | `feature/rules-normalize` | Add field normalization and validators | `Normalize national ID and check its digit` · `Normalize received date and check its range` · `Normalize central and commitment numbers` · `Add closed senders list with aliases` | `test_national_id.py` (כל שורה ב־SPEC 5.2) · `test_dates.py` (כל הפורמטים מ־5.4, שנה דו־ספרתית, 31/02, עתיד, לפני 2020) · `test_numbers.py` (הסרת כפילויות בלי לשנות סדר, `606/…` עם issue ו־`raw` נשמר) · `test_senders.py` (כינויים, לא מוכר) |
| 8 | B1.1 | `feature/rules-engine` | Add review policy, apply_rules and record builder | `Add review policy and issue codes` · `Add apply_rules entry point` · `Apply user corrections and confirmations` · `Build one record per commitment number` | `test_review_policy.py` (כל קוד, info לא מסמן, `confirmed` מסיר את `needs_review` ומשאיר את ה־issue) · `test_engine.py` (golden files, idempotent, `raw` לא משתנה, issues מהלקוח לא נלקחים בחשבון) · `test_build_records.py` (2×3 נותן 2, בלי התחייבות נותן 1 עם `REQUIRED_MISSING`, סדר) |
| 9 | B1.2 | `feature/records-repo` | Add records repository on Postgres | `Save page, image and records in one transaction` · `Get and list records with search and filters` · `Build normalized search text` · `Update fields with version check and approve` · `Delete pending records and read page image` | `test_repo.py`: הלוך־חזור שווה, אפסים מובילים, חיפוש חלקי בת״ז, במרכזי ובשם עם ״ ו־", כל מסנן ושילובים, total ו־counts, escape ל־`%`/`_`, version ישן, אין מחיקה של מאושרת, cascade |
| 10 | B1.3 | `feature/records-service` | Add record service for save, patch and approve | `Save extracted page as records` · `Patch record and update sibling records` · `Flag duplicate commitment numbers` · `Block approval while fields need review` · `Record audit events` | `test_service.py`: אישור נחסם ומחזיר שדות, עובר אחרי תיקון או `confirmed` (גם על שדה ריק), אחיות מתעדכנות, אחות מאושרת נותנת conflict, כפילות מסומנת ונפתרת ב־confirm, חריגה באמצע שמירה משאירה DB ריק, event לכל פעולה |
| 11 | B1.4 | `feature/auth` | Add login with server-side sessions | `Add users and sessions tables` · `Hash passwords with scrypt` · `Create, verify and revoke sessions` · `Add login, logout and me endpoints` · `Lock account after repeated failed logins` · `Reject cross-origin state-changing requests` · `Add create_user script` | `test_passwords.py` · `test_sessions.py` (תפוגה, ביטול, נשמר רק hash) · `test_auth_api.py` (דגלי העוגייה, אותה הודעה למשתמש לא קיים ולסיסמה שגויה, הכישלון השישי נותן `429`, שחרור אחרי 15 דקות עם שעון מוזרק, logout, Origin זר נותן `403`) · `test_create_user.py` (סיסמה קצרה נדחית) |
| 12 | B1.5 | `feature/records-api` | Expose records, page images and senders API | `Add records list and detail endpoints` · `Add patch, approve and delete endpoints` · `Add page image and senders endpoints` · `Wire routers, DB pool and auth into the app` | `test_records_api.py`: כל endpoint מחזיר `401` בלי סשן, `404`, `409` עם `type` ו־`fields`, `422`. לתמונה: `Content-Type` ו־`no-store`. `export_openapi --check` |
| 12א | B0.5 | `feature/design-tokens` | Apply design tokens from Claude Design | `Add color, type and spacing tokens from the design` · `Add base layout and status badge styles` | ידני: צילום מסך של עמוד ה־tokens ושל `StatusBadge` לצד העיצוב. `npm run build` |
| 13 | B1.6 | `feature/frontend-shell` | Add API client, login screen and app shell | `Add typed API client with problem errors` · `Add auth provider and login page` · `Add app layout, routes and error boundary` · `Add testing-library and jsdom for component tests` (D15) | `client.test.ts` (problem+json הופך ל־`ApiError`, `401` קורא ל־`onUnauthorized`, שגיאת רשת) · `LoginPage.test.tsx` (שגיאה מוצגת, `429`) · `RequireAuth.test.tsx` (הפניה לכניסה) |
| 14 | B1.7 | `feature/review-editing` | Add field editing and confirmation | `Edit field values with a local draft` · `Confirm a flagged value as is` · `Edit the central numbers list` · `Pick sender from the closed list` · `Load page image from URL in preview` (A8) | `reviewReducer.test.ts` (עריכה מסמנת `corrected` ומבטלת `confirmed`, `raw` לא משתנה, הוספה והסרה) · `FieldCell.test.tsx` (issue בטקסט ולא רק בצבע, Enter שומר, Escape מבטל) |
| 15 | B1.7 | `feature/review-approve` | Add record approval with blocking fields | `Add approve button with blocking fields` · `Handle version conflicts and approval errors` | `ApproveButton.test.tsx` (מושבת עם רשימה, `409` מציג שדות) · `useRecordMutations.test.ts` (`version_conflict` טוען מחדש ושומר את הטיוטה) |
| 16 | B1.8 | `feature/records-screen` | Add records list with search and filters | `Sync records filters with the URL` · `Add records table with pagination and counts` · `Add search box and filters` · `Add record page` | `filters.test.ts` (parse/serialize הלוך־חזור) · `format.test.ts` (`DD/MM/YYYY`, אפסים מובילים) · `RecordsPage.test.tsx` (מצב ריק, שינוי מסנן מעדכן את ה־URL) |
| 17 | B2.1 | `feature/save-extraction-records` (אם A2 קובעת ש־B כותבת) | Save extracted pages as records | `Save each extracted page through the record service` | `test_extract_records.py` עם `FakeProvider`: רשומות נשמרות כ־pending, עמוד שנכשל לא נשמר, בלי סשן מקבלים `401` |
| 18 | B2.2 | `chore/security-hardening` | Add security headers and production settings | `Add security headers middleware` · `Disable API docs in production` · `Add demo seed and wipe scripts` | `test_security.py`: הכותרות קיימות על API ועל קבצים סטטיים, `/docs` מחזיר `404` כש־`ENV=production`, `caplog`: ת״ז ושם לא מופיעים בלוגים של save ו־patch |
| 19 | B2.3 | `feature/eval-metrics` | Add evaluation against ground truth | `Load ground truth and match records` · `Compute per-field accuracy and unflagged errors` · `Write markdown evaluation report` | `test_eval.py` על CSV סינתטי קטן: exact match, שגיאה שלא סומנה נספרת, מספר רשומות מול הצפוי |
| 20 | B3.1 | `docs/submission` | Update README and PLAN for submission | `Update README for records, auth and deployment` · `Add evaluation results to README` · `Update PLAN status for submission` | — (הרצה נקייה לפי ה־README) |

**סדר המיזוג** הוא סדר הטבלה, חוץ מכמה PRs שאפשר לפתוח במקביל:

- **בלי תלויות:** 2, 7 ו־8.
- **אחרי 5 בלבד:** 11 (התחברות).
- **ה־FE:** 12א נפתח אחרי שהעיצוב אושר (B0.5). 13–16 נפתחים אחרי ש־3 ו־12א מוזגו.
- **שרשרת התלויות:** 5 → 9 → 10 → 12 → 17.
