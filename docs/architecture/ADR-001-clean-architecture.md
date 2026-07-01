# ADR-001: Clean Architecture + DDD Foundation

## Status
Accepted

## Context
EduLeague Knowledge Builder is not just a PDF reader. It is a long-term educational intelligence engine that converts learning resources into structured knowledge for AI Teacher, AI Planner, and future educational tools.

The system must support different document sources and extraction engines such as PyMuPDF, Docling, PaddleOCR, and future providers without rewriting the educational logic.

## Decision
We will separate the codebase into four main layers:

1. Domain
   - Pure educational and document models.
   - No dependency on FastAPI, Docling, PaddleOCR, or filesystem.

2. Application
   - Use cases and pipelines.
   - Coordinates domain logic and infrastructure services.

3. Infrastructure
   - Technical implementations such as PDF extraction, OCR, exporters, and storage.

4. API
   - FastAPI endpoints only.
   - No business or educational logic.

## Consequences
- Extraction engines can be replaced without changing the domain.
- AI Teacher logic can evolve independently from PDF/OCR tools.
- The project becomes easier to test, maintain, and scale.
- Initial development is slightly slower, but long-term technical debt is much lower.