# Parser And Resolution

Example:

```python
from service import submit as imported_submit

def place_order(order):
    return imported_submit(order)
```

The parser records a function declaration, an import fact and a call site. The resolver binds `imported_submit` to `service.submit` only if that symbol exists uniquely in the extracted module facts. A receiver call like `svc.submit()` remains unresolved with `unknown_receiver` because the current analyzer does not infer variable types or runtime dispatch.

Parse errors are recorded per file. A broken file does not stop the repository scan.

Markdown extraction is intentionally literal: only exact relative links such as `[service](service.py)` create `REFERENCES` edges. External links and vague prose are ignored.

`pyproject.toml` extraction records explicit project dependencies as `Dependency` nodes connected from the config node by `DECLARES_DEPENDENCY`. A declared dependency is not treated as proof that any source file imports or uses it.
