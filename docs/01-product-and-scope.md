# Product And Scope

CodeGraph helps a developer inspect source structure without running the target repository. The first implemented slice analyzes Python files and reports symbols, relationships, diagnostics and unresolved references as JSON.

This version is useful for checking whether extraction is trustworthy before adding a database or UI. It deliberately avoids claiming runtime certainty for dynamic Python behavior.

## Exclusions

- No target repository code is executed.
- No dependency installation or build script execution is performed for analyzed repositories.
- Java, TypeScript, private GitHub access, embeddings and arbitrary natural-language queries are not implemented.

## Exercise

Add a blank line above `store` in `fixtures/python_demo/service.py`, rerun the CLI, and observe that the displayed line changes while the logical ID remains based on path, kind, qualified name and signature.
