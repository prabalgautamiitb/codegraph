# Tech Stack

The implemented milestone uses Python 3.11+, Tree-sitter with pinned Python and Java grammar packages, Pydantic/FastAPI dependencies reserved for the next API milestone, and pytest for verification.

Tree-sitter gives repeatable syntax trees. CodeGraph still owns semantic decisions such as whether a call target is safe to resolve. This is similar to keeping controller DTOs separate from persistence entities in a Java backend: the parser facts are a boundary.

SQLite, Alembic, NetworkX, React, Vite and vis-network are selected for the planned product but are not yet wired into the runnable milestone.

Local configuration uses `.env` for backend settings and `frontend/.env.local` for Vite settings. The backend loads `.env` via `python-dotenv`; Vite loads `VITE_` variables automatically.
