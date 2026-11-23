# Dataset notes (read before reporting results)

Source file: `data/original/Combined_All_3_CSV_Files.csv` (read-only, SHA-256 in `SHA256SUMS`).
The application **never writes to this file**. `flask --app wsgi check-integrity` verifies it.

## What the uploaded file actually contains
It differs from the description in the project brief. These are facts measured from the uploaded file:

| Brief said | File contains |
|---|---|
| 14 columns | **13 header columns** (3 have blank headers) |
| Columns "Problem in English/Tamil", "Remedy ... in tamil" | Only: SNo, Symptoms in English/Tamil, Problem faced in English/Tamil, Remedy for problem in English/Tamil, Author, Book, Risk level, and three blank-header columns |
| "Risk level" and "Risk Level" both present | One `Risk level` column, plus a **blank-header column that holds the risk label for exactly 50 records** whose `Risk level` cell is empty |
| 5,649 records | 5,649 records (confirmed) |

## Handling (programmatic, non-destructive)
* Headers are matched by normalised name; blank-header columns whose values are all valid risk labels are treated as an auxiliary risk column.
* **Per-record risk rule:** use the first non-empty risk column in order (`Risk level`, then the blank-header column). Status is recorded per record: `ok`, `fallback` (50 records), `missing`, `invalid`, `conflict`.
* **Conflicts are flagged, not resolved:** `risk=None`, `risk_status=conflict`, and the record is withheld from remedy display. (Current file: 0 conflicts.)
* Label case variants (`low`, `medium`) are normalised **in memory only**.
* No record is deleted, merged or edited. Several remedies per problem are all preserved and ranked separately.
* Report: `flask --app wsgi data-report` writes `data/reports/data_quality.json`.

## Known data characteristics worth stating in the paper
* Each record carries a single symptom phrase, so "symptom matching" works by comparing the user's symptoms with the symptoms documented across all records of a problem (problem-group coverage).
* Some records may look clinically odd (e.g. a remedy that does not obviously match its problem). They are preserved as collected; expert review of the test set is the right place to flag them.
* The dataset's Low/Medium/High labels are **not** used for triage. They are shown as "dataset label (not clinically validated)"; records labelled High are not shown as home remedies.
