# PRISM_INTEGRATED Git Release Readiness Report

- **Audit date:** 13 October 2026 (Asia/Kolkata)
- **Working directory:** `PRISM_INTEGRATED`
- **Branch:** `freia-hazel-merge`
- **HEAD observed:** `bd37366d`
- **Local `origin/main` ref observed:** `1bf7bffd` (no fetch performed)

## A. Git status

The final index contains **263 paths**: 209 additions, 50 modifications, and 4 staged deletions. There are no unstaged tracked-file changes. Twenty-two previously untracked raw test/build/browser reports under `docs/` remain on disk; they are now individually ignored and none is included in the index. The existing `backend/storage/` and `data/testing/` contents remain on disk and are excluded from the index.

The four deletions under `data/real world/` remain staged as requested. The staged additions include **73 PDFs in explicitly synthetic test-fixture locations**; the four removed real-world items are not release additions.

## B. Changes made

- Extended the root `.gitignore` while restoring and retaining its earlier Python bytecode, environment, OCR temporary, Phase 4 generated-data, editor, and operating-system exclusions. Added explicit rules for nested environments/caches, secrets, runtime storage, local `data/testing/`, private real-evidence inputs, build/output/log files, generated browser-test output, and the observed generated document-preview/report paths.
- Updated `prism-frontend/.gitignore` to exclude demo runtime state and local environment files while preserving `.env.example`.
- Reviewed `.gitattributes`; its existing PDF, PNG, JPEG, and pickle binary classifications were retained. No attributes change was needed.
- Corrected EOF-only whitespace in 12 staged source/documentation files. Markdown metadata was changed to list formatting where trailing spaces had been used as hard line breaks. Generated test logs and raw test output were excluded instead of edited.
- Unstaged **914 previously staged runtime/local/generated paths** from the index: 803 uploaded-storage PDFs, 99 local testing files, 4 generated test log/XML files, and 8 generated report/browser-evidence files. These index-only removals preserved the local files.
- Added this report to the index after checking it for private values.

## C. Files excluded from the release index

- `backend/storage/`: **803** uploaded/runtime PDFs; preserved locally, ignored, and not staged.
- `data/testing/`: **99** local testing files; preserved locally, ignored, and not staged. Approved synthetic fixtures for the release remain in the separate backend and `tests/fixtures/` test-fixture trees.
- Generated Phase 2 pytest logs/results and raw diagnostic text/screenshots: **12** previously staged files unstaged; exact observed generated preview folders are now ignored. Local evidence was not deleted.
- Twenty-two other raw text logs/reports that were already untracked are individually ignored; they remain in the working copy and were not opened or staged.
- No virtual environment, `node_modules`, frontend `dist`, local `.env`, backend runtime storage, or `data/testing/` path is staged. No staged path matched the high-confidence private-key/API-token patterns checked. This pattern check is a narrow check, not a guarantee that every possible secret format has been detected.
- The 22 raw log/report files listed in `.gitignore` remain on disk but are excluded from staging; review them only if their evidence is needed for a later release record.

## D. Preserved components

The staged change set still contains FastAPI routes and services; auth/consent and borrower/lender workflows; bank statement ingestion and credit-card extraction; bank cash-flow features and frozen Phase 2F artifacts; PostgreSQL migrations; frontend dashboards and assessment screens; both JSON locale files; contract and backend tests; and labeled synthetic demonstration fixtures. The staged path audit found 7 route files, 2 new migrations, 5 feature files, 10 Phase 2F artifact files, 32 frontend source files, 2 locale files, 16 test-named files, and 29 files under `tests/fixtures/`.

The three staged PDF fixture groups are `backend/test_fixtures/`, `backend/phase2/outputs/synthetic_statement_fixtures/`, and `tests/fixtures/`; their fixture READMEs identify them as fictional/synthetic. No real-world statement was added to the staged snapshot.

## E. Validation results

- `git diff --cached --check`: **passed**, zero whitespace errors after cleanup.
- Backend full collection, `python -m pytest -q`: **blocked during collection** because `backend/phase2/feature_compatibility/protected_hashes_before.json` is missing. The Phase 2C test reads this file at module import, before any tests run.
- Protected-hash provenance investigation: the requested path is absent from all reachable Git objects and no generator targets that path. The Phase 2C test file’s tracked history introduces the reference without the manifest. Other manifests/generators exist for Phase 2D, 2E, 2F, 2G, and recovery snapshots, but they cover distinct scopes and do not establish the Phase 2C pre-audit baseline. No manifest was copied, synthesized, or regenerated; frozen scoring artifacts were left unchanged. Restore requires the approved original baseline from its owner/source.
- Broad database-independent backend batch across windowing, semisynthetic, Phase 2B, credit-evidence, Phase 2E, and Phase 2F modules: **212 passed, 8 failed, 3 errors**. The failures/errors require absent Berka source or derived audit files and include a legacy assertion expecting a different `scoring/artifacts/manifest.json` hash. These are reported as blockers; no test data or frozen artifacts were fabricated or rewritten.
- Clean, self-contained backend batch (`test_bank_health_index.py`, windowing, Phase 2E parser, Phase 2F scoring/reliability, and credit-evidence contracts excluding only its frozen-hash inventory test): **186 passed, 1 deselected**. No PostgreSQL was used.
- Targeted bank-layout, identity, lender, borrower-history, and validated-dossier checks with an isolated pytest temporary directory: **23 passed, 11 errors**. The errors occurred when tests attempted to connect to the configured local PostgreSQL service; the sandbox denied the local socket connection. No database-backed result is validated by this run.
- Frontend Node unit/contract tests: **13 passed** across the assessment contract, lender contract, and assessment workflow suites.
- Frontend lint (`npm run lint`): **passed**, with zero errors and zero warnings. The Playwright files explicitly import Node’s `process`; unused locals/imports were removed; lender data-loading effects now track the session ID they use.
- Frontend production build (`npm run build`): **passed**. Vite still reports stale Browserslist data and a JavaScript chunk larger than 500 kB; these are non-failing build warnings.
- Browser end-to-end tests were not run because they require live local services and can affect persisted application state.

## F. Security assessment

Commit `a81b5a9` is an ancestor of `freia-hazel-merge`. It added **four real-world financial documents** under `data/real world/`. Their four removals are staged now, but the sensitive files remain in reachable Git history. A deletion in the current index or a new deletion commit does not remove them from history.

**Do not push `freia-hazel-merge` or publish its history.** The previously specified human-controlled release path is a clean squash-style integration based on `origin/main`, without importing this branch’s sensitive intermediate history. That operation was not performed. No commit, push, merge, branch switch, fetch, or GitHub change was made during this audit.

The local environment file is excluded from the index. The database-backed checks could not connect, so database privacy and access behavior were not revalidated here.

## G. Final verdict

**BLOCKED**

The staging index is free of the identified runtime uploads, private local testing data, local environment files, generated preview directories, and whitespace errors. However, the branch still reaches the historical financial-document commit; the Phase 2C baseline is unavailable; several legacy backend checks lack their expected data/artifact inputs; and PostgreSQL-backed integration checks could not connect to an authorized isolated test database. The staged whitespace check, frontend lint, tests, and build do not resolve those release blockers.

### Human next steps

1. Keep `freia-hazel-merge` local; do not push it.
2. Have the release owner perform the planned clean squash-style integration from `origin/main` without importing the sensitive commit ancestry.
3. Obtain the original Phase 2C protected-hash baseline from its approved owner/source; do not derive it from current artifacts. Also provide the missing approved Berka inputs/derived audit outputs or document their exclusion, then rerun backend collection and relevant checks.
4. Run database-backed integration and browser acceptance only in an environment configured with an authorized isolated PostgreSQL test database and disposable data.
5. Keep the ignored raw test/browser reports out of a blanket staging action; preserve them locally and review only if their evidence is needed.
6. Recheck the final staged names, sensitive-path scan, and history boundary immediately before the human-controlled release.
