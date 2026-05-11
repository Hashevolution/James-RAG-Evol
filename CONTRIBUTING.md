# Contributing to PROJECT JAMES

Thank you for your interest in contributing! This is an early-stage research project, and contributions are welcome.

---

## Quick Start for Contributors

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR-USERNAME/James-RAG-Evol
cd James-RAG-Evol
```

### 2. Setup Development Environment

```bash
# Copy environment template
cp .env.example .env
# Edit .env with development values

# Install dependencies
pip install -r requirements.txt

# (Optional) Install dev dependencies
pip install pytest black ruff
```

### 3. Run Tests

```bash
# Diagnostic suite (65 items, 8 sections)
python james_diagnostic.py

# Security suite (83 items)
python james_security_test.py

# E2E
python james_e2e_test.py
```

### 4. Make Changes and Test

```bash
# Format code
black .

# Lint
ruff check .

# Test your changes
python <relevant_test>.py
```

### 5. Submit a Pull Request

- Branch name: `feature/short-description` or `fix/short-description`
- Reference issue number if applicable
- Describe what changed and why
- Include test results

---

## Where to Start

### Easy First Contributions

- **Documentation improvements** — README, code comments, tutorials
- **Translations** — i18n keys in `frontend/static/i18n.js`
- **Bug fixes** — check Issues tagged `good first issue`
- **Test coverage** — add tests for uncovered modules
- **Examples** — sample wikis, sample integrations

### Medium

- **New tool integrations** — see `tools/` for examples
- **LLM provider support** — add to `llm/providers/`
- **Performance improvements** — profile and optimize
- **UI enhancements** — `frontend/`

### Advanced

- **Ontology extensions** — new relation types
- **Self-evolution improvements** — Patch Pipeline robustness
- **Graph DB backend** — Neo4j integration (v0.3 priority)
- **Multi-agent system** — agent orchestration (v0.3 priority)

---

## Code Style

### Python

- **Formatter**: `black` with default settings
- **Linter**: `ruff`
- **Type hints**: encouraged but not strict (yet)
- **Docstrings**: Google style for public APIs

```python
def example_function(query: str, top_k: int = 5) -> list[dict]:
    """Search the knowledge graph.

    Args:
        query: Natural language query
        top_k: Maximum number of results

    Returns:
        List of result dicts with 'content' and 'score' keys
    """
    ...
```

### JavaScript

- **Style**: Vanilla JS, no build tools required
- **Formatting**: 2-space indent, single quotes for strings
- **i18n**: All user-facing strings via `t()` function

### Markdown / Documentation

- Use clear headings hierarchy
- Code blocks must specify language for syntax highlighting
- Keep line length reasonable (~100 chars)

---

## Architecture Principles

When contributing, please respect these principles:

### 1. Security First
Every change must consider security implications:
- Does it introduce new attack surface?
- Does it bypass existing security checks?
- Should new sensitive data be added to ABAC gating?

### 2. Fallback Always
External dependencies (LLM, web search, etc.) **will fail**. Every integration needs a fallback path:
- Cache → second LLM → static response
- Tavily → DuckDuckGo → empty results
- Graph traversal → vector-only → "no data"

### 3. Explicit Over Implicit
- Type-annotate function signatures
- Name boolean parameters clearly (`is_admin=True`, not `flag=True`)
- Log meaningful events (`[GRAPH] DFS depth=3 score=0.65`)

### 4. Backward Compatibility
v0.x allows breaking changes, but please:
- Document them in CHANGELOG.md
- Provide migration path when possible
- Announce in advance for major refactors

---

## Pull Request Process

1. **Fork** the repository
2. **Branch** from `main`
3. **Implement** your changes — new features and bug fixes are expected to include or update tests under `test/` or the `james_*_test.py` suites
4. **Run** the test suite — all must pass
5. **Commit** with clear messages (see below)
6. **Push** to your fork
7. **Open** a Pull Request against `main`

### Commit Message Format

Following [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description>

<longer description if needed>

<footer with issue references>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```
feat: add Anthropic Claude provider

Adds llm/providers/claude_client.py with streaming support.
Closes #42

fix: prevent injection through wiki frontmatter

Sanitize entity names before YAML parsing.
Discovered during security review.
```

---

## Reporting Issues

### Bug Reports

Include:
- JAMES version
- Python version
- OS
- Steps to reproduce
- Expected vs actual behavior
- Relevant log output (with sensitive data redacted)

### Feature Requests

Include:
- Use case (what problem does this solve?)
- Proposed solution
- Alternatives considered
- Willingness to implement

### Security Issues

**Do NOT open public issues for security vulnerabilities.**
See [SECURITY.md](SECURITY.md) for the responsible disclosure process.

---

## Code Review

All PRs are reviewed before merging. Reviewers check:

- Does it solve the stated problem?
- Are there security implications?
- Is it tested?
- Is it documented?
- Does it follow project conventions?
- Is the code maintainable?

Don't be discouraged by review feedback — it's how we build a quality codebase together.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

## Code of Conduct

Be respectful. Disagree with ideas, not people. Help newcomers. Assume good intent.

This is a research project — explore, experiment, ask questions.

---

## Questions?

- GitHub Discussions: general questions
- GitHub Issues: bugs and features
- Direct contact: see maintainer profile

Thank you for helping make PROJECT JAMES better!
