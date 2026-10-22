# frontend

React + TypeScript + Vite, מימין לשמאל. הטיפוסים של ה־API נוצרים מ־`backend/openapi.json` (`npm run gen:api`), וה־CI בודק שהם מעודכנים.

| תיקייה | מה יש בה |
|---|---|
| `src/features/auth/` | מסך הכניסה ושמירה על הנתיבים |
| `src/features/landing/` | דף הפתיחה |
| `src/features/upload/` | העלאת קבצים והתקדמות לכל קובץ |
| `src/features/review/` | מסך הבדיקה: תיקון שדות, אישור, אישור של כל המוכנות, מחיקה |
| `src/features/preview/` | העמוד המקורי ליד הרשומה, עם סימון המקום שבו נקרא הערך |
| `src/features/records/` | מסך הרשומות: חיפוש, סינון, מיון, היסטוריה וייצוא |
| `src/api/` | הלקוח והטיפוסים שנוצרו |
| `src/shared/` | רכיבים משותפים |

התקנה, הרצה ובדיקות: [README הראשי](../README.md#התקנה-והרצה).
