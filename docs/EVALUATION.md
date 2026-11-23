# Reproducible evaluation procedure

## 0. Environment
Use the real embedding model (`EMBEDDING_BACKEND=sentence-transformers`). Results produced with `hash` are flagged "NOT FOR PUBLICATION" in the report.

```powershell
flask --app wsgi build-index --force
flask --app wsgi calibrate-thresholds     # choose RETRIEVAL_MIN_* then record them in .env
flask --app wsgi data-report
```

## 1. Retrieval (A)
1. `flask --app wsgi make-testset-template` -> `data/eval/retrieval_testset_TEMPLATE.csv` (DRAFT; relevant_snos empty).
2. Qualified Ayurveda/medical experts rewrite each query in natural patient language (include Tamil, Telugu, Hindi), list the SNo values they judge appropriate, fill `reviewer`, set `verified=yes`; save as `data/eval/retrieval_testset.csv`. Split into dev (for tuning thresholds/weights) and test (final numbers); never tune on test.
3. `flask --app wsgi run-eval --testset data/eval/retrieval_testset.csv --k 1,3,5,10 --name final`
4. Output: `data/reports/eval_retrieval_final.{json,md}` and `_per_query.csv` with Precision@K, Recall@K, MRR, hit@K, bootstrap 95% CIs (seeded), per-language breakdown.

Systems compared: **Baseline 1** problem-name-only; **Baseline 2** symptom-aware RAG (weighted semantic ranking); **Proposed** Baseline 2 + problem-group symptom coverage + relevance thresholds + safety filtering + remedy diversification.
Note: the Proposed system may return fewer than K items (filters). P@K uses K in the denominator for all systems, which is the conservative convention; also report the no-match rate.

## 2. Generation quality (B)
Automatic proxy: `app/evaluation/generation.py::unsupported_statement_check` (numbers/records not supported by retrieved records). Manual: `app/evaluation/testset.py::write_rating_sheet` creates a sheet for expert 1-5 ratings of faithfulness, relevance, completeness and unsupported statements. Report inter-rater agreement (e.g. Cohen's kappa).

## 3. Safety (C)
`flask --app wsgi eval-safety` runs built-in **engineering regression cases** (sensitivity on HIGH cases, false-HIGH rate, under-triage count). For publication, supply a clinician-reviewed `data/eval/safety_testcases.json` (`[{"text","expected","kwargs"}]`). Unsafe-recommendation rate = share of HIGH cases that produce any remedy (must be 0; enforced by tests/test_api.py).

## 4. Multilingual (D)
Language-detection accuracy is in `eval-safety` output (per language). Retrieval per language is in the retrieval report (`by_language`). Translation quality of Telugu/Hindi remedy text: expert rating sheet; the system already rejects translations whose numbers differ from the source. Whisper: report WER per language on a recorded, transcribed sample.

## 5. User experience (E)
Research dashboard (opt-in users only): outcome percentages (self-reported), helpfulness distribution, "used recommendation" counts. Add a SUS questionnaire for usability. **Never describe self-reported improvement as clinical accuracy or effectiveness.**

## 6. Reproducibility record
Every report stores dataset SHA-256, embedding model, thresholds, rank weights, ruleset version, seeds and timestamps.
