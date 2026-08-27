# Use `unittest` for the initial test suite

Last updated: 27.08.2026

## Summary

Use Python's built-in `unittest` framework for the initial HTTP test suite. It
keeps the project free of third-party test dependencies and runnable with a
standard Python installation.

## Context

The HTTP component has a small suite for URL parsing, server behavior, and
requests between the URL code and server. Python includes `unittest`, so the
tests run without installing a test framework.

`pytest` has shorter syntax and convenient fixtures, but it would add a
dependency before the suite needs those features.

## Decision

Keep the initial HTTP tests in `http-server/tests/` and write them with
Python's built-in `unittest` framework. Reconsider the choice if the suite
grows enough to need a different structure.

## Consequences

The tests run in a standard Python environment without a third-party test
dependency. They use more explicit setup and assertion code than a `pytest`
suite. Reconsider the framework if fixtures, plugins, or a larger suite make
the tradeoff worthwhile.

## References

- [Python `unittest` documentation](https://docs.python.org/3/library/unittest.html)
