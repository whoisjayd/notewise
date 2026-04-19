> [!IMPORTANT]
> Read `CONTRIBUTING.md` before opening this PR.
> Normal contribution PRs must target `dev`. Only maintainer-managed release PRs should target `main`.
> PRs that do not follow the contribution workflow may be closed.

## Pull Request Checklist

- [ ] I read `CONTRIBUTING.md` and followed the contribution workflow.
- [ ] This PR targets `dev` (or is an explicit maintainer-managed release PR targeting `main`).
- [ ] I ran `make ci` locally and all checks passed (`format-check`, `lint-check`, `type-check`, `deps-check`, `security`, `test-cov`).
- [ ] I added or updated tests for the behavior change.
- [ ] I updated docs for user-facing changes.
- [ ] I documented any breaking change in this PR description.

## Validation Commands

```bash
make ci
```

Optional local quality commands:

```bash
make check
make verify
make pre-commit
```

## Summary

<!-- What changed and why? -->

## Related Issue

Closes #
