# Pull Request Checklist

Thank you for contributing! Please check the following before submitting:

- [ ] **All Checks Pass**: I have run `make all` and all checks passed.
  - [ ] **Formatting**: Code formatted with `make format`
  - [ ] **Linting**: No linting errors (`make lint`)
  - [ ] **Type Checking**: No type errors (`make type-check`)
  - [ ] **Tests**: All tests pass (`make test`)
- [ ] **New Tests**: I have added tests for new features/fixes.
- [ ] **Coverage**: Test coverage has not decreased (check with `make test-cov`).
- [ ] **Documentation**: I have updated the README or docs if necessary.
- [ ] **Breaking Changes**: I have noted any breaking changes in the description.

## Quick Verification

Run this command to verify everything:
```bash
make all
```

## Description
<!-- Describe your changes here -->

## Related Issue
<!-- Link to the issue this PR closes -->
Closes #
