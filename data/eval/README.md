# Evaluation data

* `retrieval_testset_TEMPLATE.csv` -- produced by `flask --app wsgi make-testset-template`. DRAFT ONLY.
  Experts must rewrite each query in natural patient language (include Tamil/Telugu/Hindi rows),
  fill `relevant_snos` with the SNo values they judge appropriate, set `reviewer` and `verified=yes`,
  and save as `retrieval_testset.csv`.
* `safety_testcases.json` (optional) -- clinician-reviewed list of
  `{"text": "...", "expected": "high|medium|low", "kwargs": {...}}` replacing the built-in regression cases.
