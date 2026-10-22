<!--
Name prompt v2, the second read (pipeline/names.py): sent to Gemini with an enlarged
crop of the page around the patient's name. Everything outside this comment is sent
as is.

Why (22.10): on the 48 sample pages the first read got 1 of 96 name parts right, and
marked 22 wrong ones "found" ("יוסף סואעד" where the page says "ישראל ישראלי"). The
name is small cursive handwriting on a whole page. In a spike on 5 pages, the same
model read the enlarged crop right where the page read was wrong or unclear, and
said "unclear" where it still could not tell. One crop came out upside down (the
first read took the page as upright): hence the line on direction.
From the first measurement with the crop (48 pages): a name written under the ID with
no label of its own was "not_found" (part 1 p21), and a whole name in one field came
back with first and last swapped (part 1 p1): hence the lines on both.
v2 (22.10): the model still said "found" about a common name that only looks like the
handwriting. It now lists the letters it sees before the name (`letters`), and
pipeline/names.py keeps a name only when those letters spell it, every one read.
Owner: A
-->
This image is an enlarged crop of a scanned Hebrew medical form (טופס התחייבות), cut
around the place where the patient's name was read on the whole page. Read the
PATIENT's first name and last name.

- The crop may be upside down or turned sideways: read the text in whatever direction
  it runs.
- Handwriting in the crop is most likely the name even with no label of its own (it
  is often written under or next to the ID number).
- Hebrew runs right to left: when one field holds the whole name (e.g. "שם:"), the
  word on the right is written first and is the first name; the next word, to its
  left, is the last name.
- The name is usually handwritten in Hebrew cursive script (כתב יד רהוט), whose letters
  can look like Latin letters (e.g. cursive "ישראל" looks like "plce"). Read it as Hebrew
  and return it in Hebrew letters, unless it is clearly written in Latin letters.
- A printed name may be crossed out, whited out or blacked out, with a name handwritten
  over it, above it or next to it. The handwritten name is the patient's name: never
  return crossed-out or erased text, or fragments of it.
- Labels such as "שם פרטי" (first name) and "שם משפחה" (last name) tell which is which.
  Names next to "אב:" (father), "אם:" (mother), a doctor, a signature or a clerk are NOT
  the patient's name.
- letters: before you write the name, copy the letters you see, one letter per item,
  in reading order (for Hebrew, the rightmost letter first), each exactly as it is
  written. Put "?" for a letter you cannot read. Copy what is on the page, not the
  name it reminds you of: a name you know is no reason to read a letter as its letter.
  value must be exactly these letters.
- status="found" only when you are certain of every letter. Otherwise status="unclear",
  value=null, and your partial reading in evidence. If the crop shows no patient name,
  status="not_found", value=null. Never guess or complete a name.
- evidence: the label next to the name and what you see there.
