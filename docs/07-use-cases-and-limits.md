# Use Cases And Limits

Implemented use cases are limited to inspecting extracted JSON from the bundled Python fixture.

Useful now:
- Verify declarations and source spans.
- See explicit inheritance.
- See conservative unresolved call reasons.
- Import an allowlisted local repository or a public GitHub repository.
- See Markdown path references and declared `pyproject.toml` dependencies.

Not useful yet:
- Interactive onboarding graph.
- Durable repository snapshots.
- Browser source inspection.
- Complete change-impact traversal.
  The browser graph explorer exists, but change-impact-specific workflows are still minimal.

The analyzer is static and conservative. An unresolved call does not mean the call is broken, and an absent edge does not mean a function is dead.
