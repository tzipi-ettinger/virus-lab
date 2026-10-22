<!--
Name prompt v1, the second read (pipeline/names.py): sent to Gemini with an enlarged
crop of the page around the patient's name. Everything outside this comment is sent
as is.

Why (22.10): on the 48 sample pages the first read got 1 of 96 name parts right, and
marked 22 wrong ones "found" ("יוסף סואעד" where the page says "ישראל ישראלי"). The
name is small cursive handwriting on a whole page. In a spike on 5 pages, the same
model read the enlarged crop right where the page read was wrong or unclear, and
said "unclear" where it still could not tell. One crop came out upside down (the
first read took the page as upright): hence the line on direction.
Owner: A
-->
This image is an enlarged crop of a scanned Hebrew medical form (טופס התחייבות), cut
around the patient's name. Read the PATIENT's first name and last name.

- The crop may be upside down or turned sideways: read the text in whatever direction
  it runs.
- The name is usually handwritten in Hebrew cursive script (כתב יד רהוט), whose letters
  can look like Latin letters (e.g. cursive "ישראל" looks like "plce"). Read it as Hebrew
  and return it in Hebrew letters, unless it is clearly written in Latin letters.
- A printed name may be crossed out, whited out or blacked out, with a name handwritten
  over it, above it or next to it. The handwritten name is the patient's name: never
  return crossed-out or erased text, or fragments of it.
- Labels such as "שם פרטי" (first name) and "שם משפחה" (last name) tell which is which.
  Names next to "אב:" (father), "אם:" (mother), a doctor, a signature or a clerk are NOT
  the patient's name.
- status="found" only when you are certain of every letter. Otherwise status="unclear",
  value=null, and your partial reading in evidence. If the crop shows no patient name,
  status="not_found", value=null. Never guess or complete a name.
- evidence: the label next to the name and what you see there.
