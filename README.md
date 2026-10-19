# virus-lab

**מטפסי התחייבות לאקסל** — מנוע שקורא טפסים סרוקים, מצולמים וכתובים ביד, מחלץ את השדות, מסמן בעצמו איפה הוא לא בטוח, ומייצא אקסל מוכן.

אתגר בשיתוף **המעבדה המרכזית לנגיפים, משרד הבריאות** · האקתון AI קוד פתוח 2026

> 🚧 **סטטוס: בפיתוח.** המסמך מתאר את המערכת כפי שתוכננה. חלקים שעוד לא מומשו מסומנים 🚧, ותוצאות המדידה יתווספו אחרי ההרצה על טבלת האמת.

> ⚠️ **הנחיות האתגר עודכנו ב־18.10:** התוצר הוא רשומות שנשמרות במערכת (מסד נתונים, אישור, חיפוש וסינון), וייצוא לאקסל הפך לאופציונלי. ההתאמה ממתינה להחלטה — ראו [docs/SPEC.md, סעיף 0](docs/SPEC.md).

---

## הבעיה

המעבדה מקבלת כל יום דגימות מקופות החולים ומבתי החולים, ועם כל דגימה טופס התחייבות — כל מוסד בפורמט אחר, חלקם בכתב יד, עם מדבקות וחותמות. היום מישהי מקלידה את כולם לאקסל ידנית.

## מה המערכת עושה

1. **מעלים** PDF ותמונות — קובץ אחד או ערימה
2. **המערכת מחלצת** לכל טופס: שם פרטי, שם משפחה, ת״ז, מספרים מרכזיים, תאריך קבלת הדגימה, גורם שולח ומספרי התחייבות
3. **מסמנת לבדיקה** כל שדה שלא בטוח, עם סיבה — ושדה שלא נמצא נשאר ריק, לא מנוחש
4. **מתקנים או מאשרים** במקום, עם העמוד המקורי ליד הטופס; הסימון מתעדכן מיד
5. **מייצאים** Excel: שורה לכל התחייבות

---

## איך זה עובד

```
UploadPanel ──POST /api/v1/extract──► FastAPI
                                        │
  ingest → rasterize → orient → extract → assemble → normalize → validate → review_policy
  קבצים     עמוד→תמונה  תיקון    Gemini    פלט המודל   תאריכים,   ספרת      מה דורש
  לעמודים               כיוון    + סכימה   → החוזה     ת״ז        ביקורת    בדיקה
                                        │
ResultsTable + DocumentPreview ◄── JSON
        │ תיקון / אישור
        ├──POST /api/v1/validate──► apply_rules → סטטוסים מעודכנים
        └──POST /api/v1/export────► apply_rules → rows → excel → .xlsx
```

### עקרונות התכנון

| עיקרון | למה |
|---|---|
| **כל עמוד נשלח כתמונה נפרדת למודל ראייה** (`gemini-3.8-flash`, Structured Output) | הדוגמאות סרוקות בלי שכבת טקסט; עמוד שנכשל לא מפיל את השאר; כל ערך מקושר לעמוד המקור |
| **ההחלטה מה דורש בדיקה נקבעת בקוד, לא במודל** | בניסויים המודל סימן ערכים שגויים כ"נמצא" ואף המציא הסבר. הקוד בודק ספרת ביקורת, תאריכים, רשימת שולחים ושדות חסרים |
| **נקודת כניסה אחת לכללים** (`apply_rules`) | אותם כללים רצים אחרי החילוץ, אחרי כל תיקון ובייצוא — בלי לשכפל אותם ב־frontend |
| **הערך שהמודל קרא לא נדרס** (`raw`), והתיקון והאישור נשמרים בנפרד | תמיד אפשר לראות מה נקרא במקור ומה שינתה המשתמשת |
| **ספק ה־AI מאחורי ממשק** (`ExtractionProvider`) | אפשר להחליף מודל בשורת הגדרה, לפתח ולבדוק עם נתוני דמה בלי מכסה ובלי רשת |
| **שלושה מבני נתונים נפרדים:** פלט המודל, חוזה ה־API, שורת אקסל | שיפור ה־prompt לא שובר את הממשק |
| **בלי שמירה לדיסק ובלי מסד נתונים** | פרטיות: הטפסים מכילים מידע רפואי אישי. ⚠️ "בלי מסד נתונים" לבחינה מחדש בעקבות הנחיות 18.10 |
| **בלי OCR נוסף** | הטעויות שמדדנו היו בחירת מספר שגוי, לא קריאת ספרות שגויה — OCR לא פותר את זה |

האיפיון המלא — הגדרת כל שדה, כללי השורות, מדיניות הבדיקה וחוזה ה־API: **[docs/SPEC.md](docs/SPEC.md)**

---

## טכנולוגיות

| שכבה | טכנולוגיה |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python 3.13, FastAPI, Pydantic |
| AI | Google Gemini (`google-genai`), מודל `gemini-3.8-flash` |
| עיבוד מסמכים | PyMuPDF |
| Excel | openpyxl |

---

## מבנה הריפו

```
virus-lab/
├── backend/
│   ├── app/
│   │   ├── api/            # health, extract, validate, export
│   │   ├── schemas/        # api.py (החוזה), extraction.py (פלט המודל)
│   │   ├── pipeline/       # ingest, orient, assemble, service
│   │   ├── extraction/     # providers: gemini, fake, cached + prompts/
│   │   ├── rules/          # engine (apply_rules), normalize, validators, review_policy, senders.yaml
│   │   └── export/         # rows, excel
│   ├── tests/              # unit, contract, fixtures
│   ├── eval/               # ground_truth.csv, run_eval.py
│   └── spike/              # ניסוי Gemini ראשוני (לא קוד מוצר)
├── frontend/src/
│   ├── api/                # client, schema.d.ts (נוצר מ־OpenAPI)
│   ├── features/           # upload, preview, review, export
│   └── shared/ui/
├── docs/SPEC.md            # איפיון
└── PLAN.md                 # תוכנית עבודה
```

---

## התקנה והרצה

### דרישות מקדימות

- Python 3.13
- Node.js 22
- Docker Desktop (בשביל Postgres מקומי)
- מפתח Gemini API מ־[Google AI Studio](https://aistudio.google.com/)

> הפקודות למטה ל־Windows PowerShell. ב־macOS/Linux: `python3` במקום `py -3.13`, ו־`.venv/bin/python` במקום `.\.venv\Scripts\python.exe`.

### Backend 🚧

```powershell
docker compose up -d db         # מהשורש: Postgres 17 מקומי, ועוד מסד לבדיקות (virus_lab_test)
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env          # ואז להדביק את המפתחות ב־GEMINI_API_KEYS
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

בדיקה: `http://localhost:8000/api/health` מחזיר `{"status": "ok", ...}`. תיעוד ה־API: `http://localhost:8000/docs`.

**משתמש:** אין הרשמה. אחרי שהשרת עלה פעם אחת (הוא יוצר את הטבלאות), יוצרים משתמש. הסיסמה נקלטת מ־prompt, לפחות 12 תווים:

```powershell
.\.venv\Scripts\python.exe -m scripts.create_user dana --name "דנה"
```

ב־Windows צריך להשאיר את `--reload`: בלעדיו uvicorn רץ על event loop ש־psycopg לא תומך בו במצב async. `docker compose down -v` מוחק את כל הנתונים המקומיים.

### Frontend 🚧

```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

פותחים `http://localhost:5173`.

### בדיקות לפני PR (אותן בדיקות שה־CI מריץ)

```powershell
# backend/ (pytest צריך את ה־Postgres מ־docker compose)
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m scripts.export_openapi --check   # אחרי שינוי בחוזה: בלי --check, ואז npm run gen:api

# frontend/
npm run lint
npm run build
npm test
```

### עבודה בלי מפתח ובלי מכסה

```powershell
# backend/.env
EXTRACTION_PROVIDER=fake
```

השרת מחזיר תוצאות שמורות מ־`tests/fixtures/` — מתאים לפיתוח הממשק ולבדיקות.

### פריסה (Render)

השרת החי הוא image אחד של Docker ([Dockerfile](Dockerfile)): Node בונה את `frontend/dist`, ו־FastAPI מגיש גם את ה־API וגם את הדף מאותה כתובת, כך שאין CORS והעוגייה של הסשן עובדת. [render.yaml](render.yaml) מגדיר את השרת ואת ה־Postgres, שניהם בתוכנית החינמית ובפרנקפורט. כל מיזוג ל־`main` נפרס אוטומטית.

**פעם ראשונה:**

1. ב־Render: **New → Blueprint**, ובוחרים את הריפו. ל־Render צריכה להיות גישה לריפו דרך ה־GitHub App שלו, ואת זה מאשרת בעלת הריפו.
2. Render מבקש את הערכים שלא נמצאים בריפו:
   - `GEMINI_API_KEYS`: המפתחות, מופרדים בפסיקים.
   - `FRONTEND_ORIGIN`: הכתובת הציבורית, למשל `https://virus-lab.onrender.com`. בקשה שמשנה נתונים ומגיעה מכתובת אחרת נדחית (CSRF).
3. אחרי שהשרת עלה (הוא יוצר את הטבלאות), יוצרים משתמשים מהמחשב, מול ה־**External Database URL** מעמוד ה־DB ב־Render:

   ```powershell
   # backend/
   $env:DATABASE_URL = "<External Database URL>?sslmode=require"
   .\.venv\Scripts\python.exe -m scripts.create_user dana --name "דנה"
   Remove-Item Env:DATABASE_URL
   ```

4. בדיקה: `https://<הכתובת>/api/health` מחזיר `"status": "ok"` ו־`"extraction_provider": "gemini"`.
5. **השרת לא נרדם:** השרת פונה לכתובת הציבורית של עצמו כל 10 דקות ([app/keep_alive.py](backend/app/keep_alive.py)), בלי הגדרה נוספת. בלוגים של Render מופיעה בקשת `GET /api/health` כל 10 דקות. כדי שזה יישאר בתוך 750 השעות החינמיות בחודש, זה צריך להיות השרת החינמי היחיד ב־workspace.

**בדיקה מקומית של ה־image:**

```powershell
docker build -t virus-lab .
docker run --rm -p 8000:8000 -e EXTRACTION_PROVIDER=fake -e FRONTEND_ORIGIN=http://localhost:8000 virus-lab
```

ה־CI בונה את ה־image ובודק שהוא מגיש את ה־API ואת הדף (job `docker`).

---

## משתני סביבה

### `backend/.env`

| משתנה | ברירת מחדל | תיאור |
|---|---|---|
| `GEMINI_API_KEYS` | — | **חובה** כש־`EXTRACTION_PROVIDER=gemini`. מפתח אחד לכל פרויקט ב־Google, מופרדים בפסיקים. כשהמכסה היומית של מפתח נגמרת, עוברים למפתח הבא. לא נכנס ל־Git |
| `GEMINI_API_KEY` | — | השם הישן למפתח יחיד. עדיין נקרא, ונוסף אחרי `GEMINI_API_KEYS` |
| `GEMINI_MODEL` | `gemini-3.8-flash` | החלפת מודל בלי שינוי קוד |
| `GEMINI_THINKING` | `low` | `low` / `medium` / `high` |
| `EXTRACTION_PROVIDER` | `gemini` | `gemini` / `fake` 🚧 |
| `EXTRACTION_CACHE` | `false` | מטמון לפיתוח בלבד, על קובצי דוגמה בלבד: עמוד ש־Gemini כבר קרא (אותו מודל ואותו prompt) נלקח מ־`backend/.cache/` בלי פנייה חדשה. לא בשרת החי |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | הכתובת של הדף: CORS בפיתוח, ובדיקת ה־`Origin` (CSRF) על בקשה שמשנה נתונים. בשרת החי: הכתובת הציבורית |
| `ENV` | `development` | `production` בשרת החי (מ־`render.yaml`): HSTS, ובלי `/docs` ו־`/openapi.json` |
| `DATABASE_URL` | — | Postgres. מקומית: מ־`docker compose`, כמו ב־`.env.example`. בשרת החי: ה־Internal URL של Render, שמגיע מ־`render.yaml`. בלעדיו השרת עולה, אבל כניסה ורשומות מחזירות `503` |
| `STATIC_DIR` | ריק | תיקיית ה־frontend הבנוי, ש־FastAPI מגיש. מוגדר רק ב־image של Docker. בפיתוח Vite מגיש את הדף |
| `KEEP_ALIVE_URL` | ריק | הכתובת הציבורית שהשרת פונה אליה (`/api/health`) כדי ש־Render לא ירדים אותו. כשהוא ריק משתמשים ב־`RENDER_EXTERNAL_URL`, ש־Render מגדיר בעצמו. בלי שניהם (מקומית ובטסטים) הפנייה כבויה |
| `KEEP_ALIVE_INTERVAL_S` | `600` | כל כמה שניות לפנות. לפחות 60. Render מרדים שרת חינמי אחרי 15 דקות בלי בקשות מבחוץ |
| `MAX_FILE_MB` | `20` | גודל קובץ מקסימלי 🚧 |
| `MAX_CONCURRENCY` | `4` | עמודים שמעובדים במקביל 🚧 |

### `frontend/.env.local`

| משתנה | ברירת מחדל | תיאור |
|---|---|---|
| `VITE_API_BASE_URL` | ריק | ריק בפיתוח: הבקשות הולכות ל־`/api`, וה־proxy של Vite מעביר אותן ל־`http://localhost:8000`. ממלאים רק כשה־frontend וה־backend בכתובות שונות. **לא לשים כאן מפתחות** — כל `VITE_*` מגיע לדפדפן |

---

## API

| Method | Path | תיאור |
|---|---|---|
| `GET` | `/api/health` | בדיקת חיים |
| `POST` | `/api/v1/extract` | `multipart/form-data` עם `files` → טפסים עם שדות, סטטוסים ותצוגה מקדימה |
| `POST` | `/api/v1/validate` | טופס אחרי תיקון או אישור → אותו טופס עם סטטוסים שחושבו מחדש |
| `POST` | `/api/v1/export` | טפסים אחרי תיקון → `.xlsx` |

החוזה המלא ודוגמאות: [docs/SPEC.md §9](docs/SPEC.md#9-חוזה-api).

---

## בדיקות ומדידה 🚧

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest                # בדיקות יחידה וחוזה
.\.venv\Scripts\python.exe eval\run_eval.py         # מדידה מול טבלת האמת
```

### תוצאות

> יתמלא אחרי ההרצה על 10–15 טפסים מול `eval/ground_truth.csv`. נדווח דיוק לפי שדה, כיסוי, **שגיאות שלא סומנו לבדיקה**, נכונות מספר השורות וזמן לעמוד.

### מה כבר נמדד (ניסוי ראשוני, 8 עמודים)

נקודת התחלה בלבד — מול קריאה ידנית ולא מול טבלת אמת מאומתת:

- **מספר מרכזי:** נכון ב־7 מתוך 8, כולל עמודים עם 2 ו־3 מרכזיים. המודל לא התבלבל במדבקות של מעבדות אחרות
- **מספר התחייבות:** זוהה נכון גם בכינויים "דרישה", "מספר דגימה" ו"אסמכתא"
- **הטעויות:** כולן בחירת מספר שגוי (מספר "מקרה" במקום ת״ז, שם האב במקום שם המטופל) — לא קריאת ספרות שגויה
- **עמודים מסובבים:** איבדו שדות בכתב יד; נוספה לולאת תיקון כיוון
- **זמן:** 4–9 שניות לעמוד ב־`thinking=low`. `medium` היה איטי פי 4 בלי שיפור

---

## מגבלות ידועות

- **שמות:** בטפסי הדוגמה הוחלפו בשרבוט, ולכן הדיוק בשמות לא נמדד
- **סימון בטוש צהוב:** כמעט כל שדות הדוגמה מסומנים בצהוב, והמודל נעזר בזה. בטפסים בלי סימון הדיוק עשוי להיות נמוך יותר
- **טופס רב־עמודי:** כל עמוד מטופל כטופס נפרד
- **מכסה:** ב־free tier של Gemini יש 20 בקשות ביום לפרויקט — לא מספיק לשימוש אמיתי
- **אין ניסיון חוזר לעמוד בודד:** עמוד שנכשל, או שלא נקרא כי המכסה נגמרה באמצע קובץ, מוצג ברשימת העמודים שנכשלו. שליחה חוזרת של כל הקובץ תיצור פעמיים את הרשומות של העמודים שכבר נשמרו
- **העלאה שנקטעה:** אחרי שגיאת רשת או שגיאת שרת באמצע העלאה אי אפשר לדעת אילו עמודים נשמרו, ולכן אין "נסי שוב". בודקים במסך הרשומות לפני שמעלים שוב
- **הסבר המודל (`evidence`)** אינו הוכחה; תמיד לבדוק מול העמוד המקורי
- **צילומי iPhone בפורמט HEIC** לא נתמכים; יש לשמור כ־JPG

## מה נדרש כדי שהמעבדה תשתמש בזה

1. **חשבון בתשלום** אצל ספק ה־AI — כדי שהקלט לא ישמש לאימון, ובשביל מכסה מספקת
2. **אישור אבטחת מידע** של הארגון לשליחת מידע רפואי לספק חיצוני, או מעבר למודל שרץ בתוך הרשת
3. **מדידה על טפסים אמיתיים** (בלי סימון צהוב), בהשתתפות הצוות
4. **פורמט האקסל המדויק** שהמעבדה עובדת איתו
5. **ניהול הרשימה הסגורה** של גורמים שולחים על ידי המעבדה

---

## פרטיות ואבטחה

- עובדות **רק עם קובצי הדוגמה של האתגר**, שבהם הפרטים האישיים שונו
- הקובץ שהועלה עובר **בזיכרון בלבד** ולא נשמר. נשמרות רק הרשומות ותמונה דחוסה של כל עמוד, ב־PostgreSQL מנוהל של Render (Frankfurt, האיחוד האירופי). פירוט ב־[SPEC 11.1](docs/SPEC.md#111-פרטיות-ואבטחה)
- הלוגים לא מכילים שמות, ת״ז או תוכן טפסים: ה־access log נכתב בלי ה־query של החיפוש, ושגיאה לא צפויה נרשמת רק לפי הסוג והנתיב, בלי ההודעה וה־traceback
- **כניסה:** משתמשים מוגדרים מראש בלבד, סיסמאות ב־scrypt, עוגיית סשן `HttpOnly; Secure; SameSite=Strict`, נעילה אחרי 5 ניסיונות, ובדיקת `Origin` על כל שינוי
- **כותרות:** CSP שמתיר רק את האתר עצמו, `nosniff`, `no-referrer`, איסור הטמעה במסגרת, ו־HSTS בשרת החי. תשובות ה־API לא נשמרות במטמון (`no-store`)
- **בשרת החי** (`ENV=production`): אין `/docs` ואין `/openapi.json`
- **מחיקה בפקודה אחת:** `python -m scripts.wipe_data` מוחק את כל העמודים, התמונות והרשומות. המשתמשים נשארים
- מפתח ה־API רק ב־`backend/.env` ובמשתני הסביבה של Render; הקבצים `.env` ותוצאות הניסויים מוחרגים מ־Git

### בדיקה לפני הגשה

```powershell
curl.exe -I https://<הכתובת>/                       # CSP, nosniff, no-referrer, X-Frame-Options, HSTS
curl.exe -s -o NUL -w "%{http_code}" https://<הכתובת>/docs           # 404
curl.exe -s -o NUL -w "%{http_code}" https://<הכתובת>/api/v1/records # 401 בלי כניסה
```

ואחר כך, בלוגים של Render: חיפוש לפי ת״ז במסך הרשומות לא משאיר את המספר בלוג.

### נתוני הדגמה ומשתמש לשופטים

```powershell
# backend/, עם ה־External URL של ה־DB ב־Render (כמו ב־create_user)
.\.venv\Scripts\python.exe -m scripts.create_user judge-demo --name "שופטים"
.\.venv\Scripts\python.exe -m scripts.seed_demo "<תיקיית קובצי הדוגמה>" --user dana   # רק קובצי הדוגמה של האתגר
.\.venv\Scripts\python.exe -m scripts.wipe_data                                   # להתחיל מחדש
```

`seed_demo` קורא כל קובץ כמו העלאה באתר ושומר את הרשומות כממתינות. `EXTRACTION_CACHE=true` חוסך מכסה על עמודים ש־Gemini כבר קרא. את פרטי הכניסה של `judge-demo` מוסרים בטופס ההגשה, לא כאן (D9).

---

## עבודה בצוות

| | אחריות |
|---|---|
| **מפתחת A** | קליטת קבצים, עיבוד עמודים, חילוץ AI, `assemble`, `UploadPanel`, `DocumentPreview` |
| **מפתחת B** | נרמול, ולידציה, מדיניות בדיקה (`apply_rules`), `validate`, שורות ו־Excel, `ResultsTable`, ייצוא |
| **משותף** | חוזה ה־API (`schemas/api.py`), טבלת האמת, בדיקות קצה לקצה |

- ענף לכל משימה (`feature/<name>`), מיזוג ל־`main` רק דרך Pull Request
- שינוי בחוזה — רק ב־PR משותף שמעדכן את שני הצדדים
- תוכנית העבודה והחלטות פתוחות: [PLAN.md](PLAN.md)
