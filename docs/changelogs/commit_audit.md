## [35b8b65] fix: improve model fetching logic in setup wizard
**Date**: Fri Feb 06 11:16:39 2026 +0530
**Files**:

M	src/yt_study/setup_wizard.py

## [a6ba29f] fix: update web visualizer default port to 8000 to match documentation
**Date**: Fri Feb 06 11:09:44 2026 +0530
**Files**:

M	src/yt_study/ui/web.py

## [5d73ccb] docs: sync README with docs/index.md to ensure consistency
**Date**: Fri Feb 06 11:09:30 2026 +0530
**Files**:

M	README.md

## [77b435a] chore: final cleanup
**Date**: Fri Feb 06 11:02:06 2026 +0530
**Files**:

M	docs/changelogs/release_notes.md
M	docs/changelogs/session_changes.md

## [1e8d746] docs: polish documentation structure and visuals
**Date**: Fri Feb 06 10:40:24 2026 +0530
**Files**:

M	README.md
D	docs/Architecture.md
D	docs/CONTRIBUTING.md
D	docs/Configuration.md
D	docs/FAQ.md
D	docs/Installation.md
D	docs/Usage.md
A	docs/architecture.md
R100	COMMIT_AUDIT.md	docs/changelogs/commit_audit.md
R100	RELEASE_NOTES.md	docs/changelogs/release_notes.md
R100	SESSION_CHANGES.md	docs/changelogs/session_changes.md
R100	docs/CODE_OF_CONDUCT.md	docs/code_of_conduct.md
A	docs/configuration.md
A	docs/contributing.md
A	docs/faq.md
M	docs/index.md
A	docs/installation.md
A	docs/usage.md
M	mkdocs.yml

## [87cc72e] feat: add high-level generation tracking to generator
**Date**: Fri Feb 06 10:27:29 2026 +0530
**Files**:

M	src/yt_study/core/llm/generator.py

## [f6ee63c] feat: enable posthog session replay and llm tracking
**Date**: Fri Feb 06 10:23:51 2026 +0530
**Files**:

M	src/yt_study/core/llm/providers.py
M	src/yt_study/core/telemetry.py
M	src/yt_study/ui/web.py

## [f1098d2] docs: update changelogs with telemetry and testing details
**Date**: Fri Feb 06 10:15:39 2026 +0530
**Files**:

M	RELEASE_NOTES.md
M	SESSION_CHANGES.md

## [a30f599] test: add property-based and edge-case tests
**Date**: Fri Feb 06 10:12:54 2026 +0530
**Files**:

M	.gitignore
M	pyproject.toml
M	src/yt_study/cli.py
M	src/yt_study/config.py
M	src/yt_study/core/telemetry.py
M	src/yt_study/setup_wizard.py
M	src/yt_study/ui/web.py
A	tests/test_edge_cases.py
A	tests/test_properties.py
M	tests/test_setup_wizard.py
M	uv.lock

## [f6f9008] refactor: fix encoding artifacts and remove wiki submodule
**Date**: Fri Feb 06 09:46:39 2026 +0530
**Files**:

M	src/yt_study/cli.py
M	src/yt_study/core/updates.py
M	src/yt_study/ui/web.py

## [cc5b565] refactor: fix encoding artifacts and remove wiki submodule
**Date**: Fri Feb 06 09:46:28 2026 +0530
**Files**:

M	.gitmodules
D	wiki

## [3e54ac8] docs: finalize session changes
**Date**: Thu Feb 05 23:02:08 2026 +0530
**Files**:

M	SESSION_CHANGES.md

## [3684a84] fix: synchronize version and update lockfile
**Date**: Thu Feb 05 22:53:57 2026 +0530
**Files**:

M	uv.lock

## [d4981f1] docs: fix character encoding issues and update documentation
**Date**: Thu Feb 05 22:53:09 2026 +0530
**Files**:

M	pyproject.toml
M	src/yt_study/cli.py
A	src/yt_study/core/updates.py

## [b6f35a5] ci: add pypi publishing and sha256 checksums
**Date**: Thu Feb 05 22:51:10 2026 +0530
**Files**:

M	.github/workflows/release.yml

## [e404473] feat: add web visualizer (yt-study serve)
**Date**: Thu Feb 05 22:47:35 2026 +0530
**Files**:

A	.pre-commit-config.yaml
M	CONTRIBUTING.md
A	SESSION_CHANGES.md
A	src/yt_study/api.py
M	src/yt_study/config.py
A	src/yt_study/core/__init__.py
A	src/yt_study/core/events.py
R100	src/yt_study/llm/__init__.py	src/yt_study/core/llm/__init__.py
R076	src/yt_study/llm/chapters.py	src/yt_study/core/llm/chapters.py
R084	src/yt_study/llm/generator.py	src/yt_study/core/llm/generator.py
R095	src/yt_study/llm/providers.py	src/yt_study/core/llm/providers.py
A	src/yt_study/core/telemetry.py
R100	src/yt_study/youtube/__init__.py	src/yt_study/core/youtube/__init__.py
R090	src/yt_study/youtube/metadata.py	src/yt_study/core/youtube/metadata.py
R100	src/yt_study/youtube/parser.py	src/yt_study/core/youtube/parser.py
R080	src/yt_study/youtube/playlist.py	src/yt_study/core/youtube/playlist.py
R093	src/yt_study/youtube/transcript.py	src/yt_study/core/youtube/transcript.py
M	src/yt_study/pipeline/orchestrator.py
M	src/yt_study/prompts/chapters.py
M	src/yt_study/setup_wizard.py
M	src/yt_study/utils.py
M	tests/conftest.py
M	tests/test_llm/test_chapters.py
M	tests/test_llm/test_generator.py
M	tests/test_llm/test_providers.py
M	tests/test_pipeline/test_orchestrator.py
M	tests/test_setup_wizard.py
M	tests/test_youtube/test_metadata.py
M	tests/test_youtube/test_parser.py
M	tests/test_youtube/test_playlist.py
M	tests/test_youtube/test_transcript.py

## [940a80a] docs: finalize mkdocs configuration and assets
**Date**: Thu Feb 05 22:40:50 2026 +0530
**Files**:

M	.gitignore
A	docs/CODE_OF_CONDUCT.md
A	docs/CONTRIBUTING.md
M	mkdocs.yml
M	src/yt_study/cli.py
A	src/yt_study/ui/web.py
M	uv.lock

## [51a403f] docs: enhance README and setup mkdocs
**Date**: Thu Feb 05 22:35:52 2026 +0530
**Files**:

M	README.md
A	docs/Architecture.md
A	docs/Configuration.md
A	docs/FAQ.md
A	docs/Installation.md
A	docs/Usage.md
A	docs/index.md
A	mkdocs.yml
M	pyproject.toml

## [1dff40c] ci: add release workflow for cross-platform builds
**Date**: Thu Feb 05 22:35:42 2026 +0530
**Files**:

M	.github/workflows/release.yml

## [150c5cc] ci: add release workflow for cross-platform builds
**Date**: Thu Feb 05 22:33:58 2026 +0530
**Files**:

M	.github/workflows/release.yml

## [c454ac9] docs: add detailed commit audit
**Date**: Thu Feb 05 22:32:54 2026 +0530
**Files**:

A	COMMIT_AUDIT.md

## [018c4f0] bump version to v0.1.9
**Date**: Thu Feb 05 20:54:26 2026 +0530
**Files**:

M	pyproject.toml
M	src/yt_study/__init__.py

## [61f3fe2] docs: update documentation for chunk+chapter pipeline
**Date**: Thu Feb 05 20:49:09 2026 +0530
**Files**:

M	README.md
M	wiki

## [6bd0fd6] feat(pipeline): add synthetic chapter engine and prepare release notes
**Date**: Thu Feb 05 20:42:38 2026 +0530
**Files**:

M	README.md
A	RELEASE_NOTES.md
M	pyproject.toml
M	src/yt_study/cli.py
A	src/yt_study/llm/chapters.py
M	src/yt_study/llm/generator.py
M	src/yt_study/pipeline/orchestrator.py
A	src/yt_study/prompts/chapters.py
A	src/yt_study/utils.py
A	tests/test_llm/test_chapters.py
M	tests/test_llm/test_generator.py
M	tests/test_pipeline/test_orchestrator.py
M	uv.lock

## [276eb7d] feat(llm): add chapter timestamp links to generated notes
**Date**: Thu Feb 05 20:00:40 2026 +0530
**Files**:

M	src/yt_study/llm/generator.py
M	src/yt_study/pipeline/orchestrator.py
M	src/yt_study/prompts/chapter_notes.py
M	src/yt_study/prompts/study_notes.py
M	src/yt_study/youtube/transcript.py
M	tests/test_llm/test_generator.py

## [98e22ba] fix(pipeline): implement rate limiting and robust filename sanitization
**Date**: Thu Feb 05 19:49:12 2026 +0530
**Files**:

M	pyproject.toml
M	src/yt_study/config.py
M	uv.lock

## [e11375e] feat(pipeline): add playlist checkpointing and transcript export
**Date**: Thu Feb 05 19:48:49 2026 +0530
**Files**:

M	src/yt_study/cli.py
M	src/yt_study/pipeline/orchestrator.py
M	tests/test_pipeline/test_orchestrator.py

## [4193287] fix(llm): implement recursive chunking for oversized chapters
**Date**: Thu Feb 05 19:48:09 2026 +0530
**Files**:

M	src/yt_study/llm/generator.py
M	tests/test_llm/test_generator.py

## [3f5db1e] docs: Update documentation to reference Makefile commands
**Date**: Tue Feb 03 16:41:39 2026 +0530
**Files**:

M	.github/pull_request_template.md
M	CONTRIBUTING.md
M	README.md
