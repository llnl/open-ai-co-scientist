# Changelog

All notable changes to the AI Co-Scientist project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- Fixed the Hugging Face Space metadata to match the pinned Gradio dependency
  and added post-push Space status polling so build/runtime errors fail the
  deployment workflow instead of being missed (loop#14).

- Automatic model fallback (llnl#26): when the configured/selected model is
  unavailable, delisted, rate-limited, or erroring, `call_llm` falls back to a
  **working free model fetched live from OpenRouter** (`fetch_free_models`, the
  source of truth) instead of failing every run. Falls back on
  model-unavailable / rate-limit / provider errors — not on auth (a different
  model won't help). Rate-limited free models are skipped immediately (SDK
  Retry-After backoff disabled) rather than blocking the run; attempts are
  bounded. A static list is a last resort only if the live fetch fails.
- Updated the default `config.yaml` model (the previous
  `google/gemini-2.0-flash-exp:free` was delisted).

### Fixed
- Generation failures no longer surface as a silent empty ranking (llnl#36).
  The real cause — missing/invalid API key, model unavailable/delisted, rate
  limiting, or unparsable model output — now appears in the run status line and
  an actionable error box in the results panel, instead of a false
  "completed successfully". Fixes a three-layer silent-failure chain where the
  error text was discarded during generation, making downstream propagation
  dead code.

### Added
- `classify_llm_error()` maps raw LLM/API errors to user-actionable categories;
  `call_llm` now distinguishes model-unavailable/delisted errors.
- Offline-by-default test suite: `integration`/`network` pytest markers, mocked
  OpenRouter boundary tests, and credential-leak regression tests.
- CI workflow (lint, offline tests, boot smoke) pinned to Python 3.12 with
  CPU-only torch.
- `pyproject.toml` (pytest + ruff config), pinned `requirements.txt`,
  `requirements-dev.txt`, `.env.example`.
- Makefile targets: `test`, `test-all`, `lint`, `fmt`, and per-issue worktree
  helpers `wt`/`wt-clean`.
- `AGENTS.md` (AI-agent instructions), `docs/loop/GOALS.md` (loop steering),
  `scripts/setup_labels.sh` (loop label state machine).

### Fixed
- `call_llm` crashed with openai>=1 when `OPENROUTER_API_KEY` was unset instead
  of returning the documented error message.
- API keys are now redacted from log lines and user-facing error text
  (`redact_secrets`).
- `similarity_score` treats whitespace-only input as empty (returns 0.0).

### Removed
- Dead FastAPI-era `tests/test_api.py` (targeted the removed `app/api.py`) and
  the stray `tests/test_graph.html` artifact.

## [1.1.0] - 2025-05-31

### Added - References Section and Literature Integration

#### 🔬 **ArXiv Integration**
- **Comprehensive arXiv API integration** for scientific literature discovery
- **Automatic paper search** based on research goal keywords (up to 5 most relevant papers)
- **Full paper metadata display** including titles, authors, abstracts, publication dates, and categories
- **Direct linking** to arXiv papers, PDF downloads, and DOI references
- **ArXiv testing interface** at `/arxiv/test` for standalone literature search functionality

#### 📚 **Smart Reference Detection**
- **Intelligent reference type detection** from LLM-generated hypothesis reviews
- **arXiv ID linking**: Automatic detection and linking of arXiv identifiers (e.g., `2301.12345`, `arxiv:1706.03762`)
- **DOI linking**: Direct links to journal articles via DOI identifiers (e.g., `10.1145/3394486.3403087`)
- **PubMed integration**: Links to biomedical literature with domain-appropriate usage warnings
- **Generic reference display**: Formatted display for paper titles, conference citations, and other references

#### 🎯 **Domain-Appropriate Literature**
- **Computer science focus**: Prioritizes arXiv papers and CS conference literature
- **Biomedical support**: Maintains PubMed integration for life sciences research
- **Cross-domain warnings**: Alerts users when PubMed references appear in non-biomedical contexts
- **Updated LLM prompts**: Modified reflection prompts to avoid inappropriate PMIDs for CS topics

#### 🎨 **Professional User Interface**
- **New References section** positioned between Results and Errors in main interface
- **Card-based paper display** with professional academic formatting
- **Category tags** showing arXiv subject classifications
- **Responsive design** elements for optimal viewing experience
- **Error state handling** with user-friendly messages and fallbacks

#### 🔧 **API Endpoints**
- `POST /arxiv/search` - Search arXiv papers with filtering options
- `GET /arxiv/paper/{id}` - Retrieve specific paper details
- `GET /arxiv/trends/{query}` - Analyze research trends over time
- `GET /arxiv/categories` - List available arXiv subject categories
- `GET /arxiv/test` - Comprehensive testing interface for arXiv functionality
- `POST /log_frontend_error` - Frontend error logging for debugging

#### 📊 **Enhanced Logging and Debugging**
- **Frontend-to-backend logging** system for comprehensive error tracking
- **Detailed reference processing logs** showing each step of literature discovery
- **ArXiv search status logging** with response codes and paper counts
- **Error handling with stack traces** for debugging JavaScript issues
- **Structured log data** with timestamps and contextual information

#### 🛠 **Technical Improvements**
- **New data models**: `ArxivPaper`, `ArxivSearchRequest`, `ArxivSearchResponse`, `ArxivTrendsResponse`
- **ArXiv search tool**: Comprehensive `ArxivSearchTool` class with filtering and analysis capabilities
- **Updated dependencies**: Added `arxiv`, `feedparser`, `python-dateutil` for arXiv integration
- **Async JavaScript functions** for non-blocking literature search
- **Regex pattern fixes** for reliable reference type detection
- **Graceful error handling** with user-friendly fallback messages

### Changed
- **Enhanced hypothesis reviews** now include domain-appropriate reference types
- **Improved LLM prompts** to generate relevant CS literature references instead of inappropriate PMIDs
- **Updated main interface** to include automatic literature discovery after each cycle
- **Modified reference display** from generic "PMIDs" to "Additional References" with smart type detection

### Fixed
- **JavaScript regex errors** in reference type detection patterns
- **Domain inappropriateness** of PubMed references for computer science research
- **Missing error handling** in frontend reference processing
- **Console errors** that prevented references section from loading properly

### Technical Details
- **Files Added**: `app/tools/arxiv_search.py`, `CHANGELOG.md`
- **Files Modified**: `app/api.py`, `app/models.py`, `app/agents.py`, `requirements.txt`, `README.md`, `claude_planning.md`
- **New Dependencies**: arxiv==2.1.0, feedparser==6.0.10, python-dateutil==2.8.2
- **API Endpoints Added**: 6 new endpoints for arXiv integration and frontend logging
- **JavaScript Functions Added**: `logToBackend()`, enhanced `updateReferences()` and `displayReferences()`

### Impact
- **Dramatically improved research quality** through automatic literature discovery
- **Enhanced user experience** with professional reference display and direct paper access
- **Better domain appropriateness** with CS-focused literature for computer science research
- **Improved debugging capabilities** with comprehensive frontend-to-backend logging
- **Scientific rigor** through integration with arXiv, the primary preprint server for CS and physics

This release transforms the AI Co-Scientist from a hypothesis-only system into a literature-integrated research platform, providing users with immediate access to relevant scientific papers and properly formatted academic references.

## [1.0.0] - 2025-02-28

### Added
- Initial release of AI Co-Scientist hypothesis evolution system
- Multi-agent architecture with Generation, Reflection, Ranking, Evolution, Proximity, and MetaReview agents
- FastAPI web interface with advanced settings
- LLM integration via OpenRouter API
- Elo-based hypothesis ranking system
- Hypothesis similarity analysis and visualization
- YAML configuration management
- Basic HTML frontend with vis.js graph visualization
