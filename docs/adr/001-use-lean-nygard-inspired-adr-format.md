# Use a lean Nygard-inspired ADR format

Last updated: 27.08.2026

## Summary

Use five sections in every architecture decision record: Summary, Context,
Decision, Consequences, and References. This is a lean format inspired by
Michael Nygard's approach.

## Context

The project has owner-specific ADR directories. The first records were short
notes without a common set of headings. A shared structure makes the decisions
easier to scan as the project grows.

Large ADR templates add status fields, option tables, implementation plans,
and verification checklists. Those fields suit larger projects but add
paperwork here. Each record still needs to explain the reason for the
decision, alternatives, boundaries, tradeoffs, and follow-up work.

## Decision

Every architecture decision record uses this order:

1. Start with a verb-led title.
2. Add `Last updated: DD.MM.YYYY` as a date stamp, not a status field.
3. Use `## Summary` for one short paragraph that states the decision.
4. Use `## Context` for the trigger, constraints, and alternatives.
5. Use `## Decision` for the chosen approach, scope, and non-goals.
6. Use `## Consequences` for tradeoffs, risks, and follow-up work.
7. Use `## References` for source material and related decisions.

Use a zero-padded number and lowercase slug for each filename. Number records
separately inside each owning `docs/adr/` directory. Put decisions that cross
component boundaries in the root `docs/adr/` directory.

Do not add status front matter, a `Status` heading, decision-owner wording, or
empty template sections. Put any needed detail inside the five sections.

Write an ADR when a decision changes the project's structure, dependencies,
interfaces, or operation. Keep routine implementation choices and status notes
in normal documentation.

When a new ADR replaces an earlier decision, link the records at the top of
each `Context` section and update their date stamps. Keep the earlier
rationale intact.

## Consequences

Every ADR has the same basic shape, while the directory layout still shows who
owns the decision. Existing decisions keep their original meaning.

The format has no status field or dedicated implementation plan section. Put
scope, non-goals, tradeoffs, follow-up work, and proof limits in the five
sections when they matter.

Larger decisions can include more detail within the same sections. A change to
the format itself requires a new ADR.

## References

- [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [AWS Prescriptive Guidance: Architectural decision record process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html)
