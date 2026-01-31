# Governance Model

## Maintainers

Maintainers are responsible for:
- Triaging new issues and PRs.
- Reviewing and merging pull requests.
- cutting releases and publishing to PyPI.
- Enforcing the Code of Conduct.

## Decision Making

Decisions are made by consensus among maintainers. If consensus cannot be reached, the project lead has the final say.

## Triage Policy

1. **New Issues**: Should be labeled with `triage` automatically (via workflow) or manually.
2. **Review**: Maintainers verify reproducibility and scope.
3. **Assignment**: Accepted issues are labeled with `type:*` and `priority:*`.
4. **Stale**: Issues with no activity for 60 days are marked stale and closed after 7 days.

## Release Process

1. Create a new GitHub Release with a tag (e.g., `v0.1.0`).
2. The `release` workflow will automatically:
   - Run full validation tests.
   - Build the package.
   - Publish to PyPI (if configured).
