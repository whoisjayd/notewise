# Commit Audit (v0.1.8..HEAD)

## [018c4f0] bump version to v0.1.9
**Date**: Thu Feb 5 20:54:26 2026 +0530
**Files**:
- `M` pyproject.toml
- `M` src/yt_study/__init__.py

## [61f3fe2] docs: update documentation for chunk+chapter pipeline
**Date**: Thu Feb 5 20:49:09 2026 +0530
**Files**:
- `M` README.md
- `M` wiki

## [6bd0fd6] feat(pipeline): add synthetic chapter engine and prepare release notes
**Date**: Thu Feb 5 20:42:38 2026 +0530
**Files**:
- `M` README.md
- `A` RELEASE_NOTES.md
- `M` pyproject.toml
- `M` src/yt_study/cli.py
- `A` src/yt_study/llm/chapters.py
- `M` src/yt_study/llm/generator.py
- `M` src/yt_study/pipeline/orchestrator.py
- `A` src/yt_study/prompts/chapters.py
- `A` src/yt_study/utils.py
- `A` tests/test_llm/test_chapters.py
- `M` tests/test_llm/test_generator.py
- `M` tests/test_pipeline/test_orchestrator.py
- `M` uv.lock

## [276eb7d] feat(llm): add chapter timestamp links to generated notes
**Date**: Thu Feb 5 20:00:40 2026 +0530
**Files**:
- `M` src/yt_study/llm/generator.py
- `M` src/yt_study/pipeline/orchestrator.py
- `M` src/yt_study/prompts/chapter_notes.py
- `M` src/yt_study/prompts/study_notes.py
- `M` src/yt_study/youtube/transcript.py
- `M` tests/test_llm/test_generator.py

## [98e22ba] fix(pipeline): implement rate limiting and robust filename sanitization
**Date**: Thu Feb 5 19:49:12 2026 +0530
**Files**:
- `M` pyproject.toml
- `M` src/yt_study/config.py
- `M` uv.lock

## [e11375e] feat(pipeline): add playlist checkpointing and transcript export
**Date**: Thu Feb 5 19:48:49 2026 +0530
**Files**:
- `M` src/yt_study/cli.py
- `M` src/yt_study/pipeline/orchestrator.py
- `M` tests/test_pipeline/test_orchestrator.py

## [4193287] fix(llm): implement recursive chunking for oversized chapters
**Date**: Thu Feb 5 19:48:09 2026 +0530
**Files**:
- `M` src/yt_study/llm/generator.py
- `M` tests/test_llm/test_generator.py

## [3f5db1e] docs: Update documentation to reference Makefile commands
**Date**: Tue Feb 3 16:41:39 2026 +0530
**Files**:
- `M` .github/pull_request_template.md
- `M` CONTRIBUTING.md
- `M` README.md
