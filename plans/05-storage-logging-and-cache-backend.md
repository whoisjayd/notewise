# Plan 05 — Storage, logging, cache lifecycle, and supporting repository methods

## Goal

Stabilize the storage and logging substrate, add schema-versioned cache lifecycle support, and provide the repository methods required by the later CLI command work.

## Governance references

- Global constraints: `master-prompt.md`
- Source-verified bug baseline: `plan-reference.md`
- Sequencing and dependencies: `plan-index.md`

## Source coverage

- V3 bug scope: `BUG-08`, `BUG-14`, `BUG-15`, `BUG-18`, `BUG-26`, `BUG-27`, `BUG-35`
- Source task coverage: `TASK-11` / storage hardening
- Older backlog carry-forward: `TASK-11c` explicit DB singleton/test-isolation audit
- Related later dependency: backend methods required by the CLI commands in Plan 06
- `plan-reference.md` anchors: `BUG-08` (line 275), `BUG-14` (line 346), `BUG-15` (line 357), `BUG-18` (line 400), `BUG-26` (line 497), `BUG-27` (line 512), `BUG-35` (line 673)
- `plan-reference.md` task anchor: `TASK-11` (line 1392), with dependency note (line 1395) and migration mapping (lines 1539-1540)

## Verified current-state findings from the codebase

- `storage/migrations.py` still only contains the one-off `repair_runstats_schema()` helper.
- `storage/models.py` still has no `cached_at` field on `VideoRecord`.
- `logging.py` still writes `_SESSION_LOG_PATH` without a lock and still recreates log files on repeated configuration.
- `setup_wizard.load_config()` still does not strip quotes.
- `utils.sanitize_filename()` still needs the reserved-name ordering fix described in the backlog.
- `tests/conftest.py` already closes DB singletons, but the limiter cleanup is a separate concern that should be added here.

## Constraints that must not be violated

1. `DatabaseRepository` must continue returning schema objects, not ORM objects.
2. The repository singleton contract must remain intact.
3. Logging in library code must remain `structlog`-based.
4. Schema changes must be additive and migratable for existing SQLite files.

## Files to modify

- `src/yt_study/storage/models.py`
- `src/yt_study/storage/migrations.py`
- `src/yt_study/storage/repository.py`
- `src/yt_study/logging.py`
- `src/yt_study/utils.py`
- `src/yt_study/errors.py`
- `src/yt_study/ui/setup_wizard.py`
- `tests/conftest.py`
- tests under `tests/unit/storage/`, `tests/unit/errors/`, `tests/unit/utils/`

## Implementation steps

### 1. Introduce schema versioning

Replace the one-off migration shape with a proper migration runner.

Required pieces:

- a `schema_version` table
- numbered migrations executed in order
- migration 1 should preserve the existing runstats additive-column repair logic
- migration 2 should add `video.cached_at`

Migration runner requirements:

- idempotent
- safe on existing DBs
- no destructive migration in this plan

### 2. Add `cached_at` to `VideoRecord`

In `models.py`:

- add a timestamp field for cache freshness tracking
- update `upsert_video_cache()` so every write refreshes `cached_at`
- ensure schema objects expose the new field only if needed by existing serializers and without breaking current callers

### 3. Add repository methods needed by later CLI commands

In `DatabaseRepository`:

- `get_recent_videos(limit=10)`
- `get_stats(since_days=None, model=None)`
- `prune_old_entries(older_than_days=30)`
- any minimal helpers required for cache-info and history displays

Keep method return values schema-safe and easy for the CLI layer to format.

### 4. Fix logging thread safety and idempotency

In `logging.py`:

- guard writes to `_SESSION_LOG_PATH` with a `threading.Lock`
- add an idempotency guard so repeated `configure_logging()` calls do not create new log files and do not reconfigure handlers unnecessarily
- preserve the ability to return the session log path

### 5. Fix setup-config parsing and filename sanitation

- In `setup_wizard.load_config()`, strip surrounding quotes from values.
- In `utils.sanitize_filename()`, apply reserved-name protection before truncation.

### 6. Fix user-error classification order

In `errors.py`:

- check auth/API-key style failures before generic permission-denied filesystem branches
- keep the user-facing wording helpful and specific

### 7. Strengthen test teardown isolation

In `tests/conftest.py`:

- keep the existing `DatabaseRepository.close_all_instances()` teardown
- add `clear_youtube_limiters()` teardown to avoid stale loop-scoped limiter state in tests

## Tests to add or update

### Unit/integration tests

- migration runner upgrades old DBs in sequence
- `cached_at` is set on insert and refreshed on update
- `prune_old_entries()` removes only stale cache rows
- repeated `configure_logging()` calls reuse the same session log configuration
- `sanitize_filename()` preserves reserved-name prefixing even at truncation boundaries
- auth-style provider errors are not misreported as local filesystem permission failures
- `load_config()` strips quoted values
- test teardown clears both DB singletons and YouTube limiters

## Exit criteria

- Cache schema is versioned and migratable.
- `VideoRecord` has a usable `cached_at` field.
- Repository methods exist for stats, history, and pruning.
- Logging is thread-safe and idempotent.
- Test isolation covers both DB instances and limiter state.

## References

- SQLAlchemy metadata and migrations: https://docs.sqlalchemy.org/en/20/core/metadata.html
- SQLAlchemy defaults and SQL expressions: https://docs.sqlalchemy.org/en/20/core/defaults.html
- structlog configuration: https://www.structlog.org/en/stable/configuration.html
- Python `logging` cookbook: https://docs.python.org/3/howto/logging-cookbook.html
