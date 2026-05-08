# Architecture

## Overview

`saas-mortgage` is a monolithic Flask application designed as a reusable foundation for future SaaS prototypes.

## Core stack

- Frontend: HTML, Jinja templates, lightweight CSS
- Backend: Python Flask
- Database: SQLite via SQLAlchemy
- Auth: Flask-Login
- Migrations: Flask-Migrate

## Design intent

- Keep the starter small enough to understand quickly.
- Preserve the reusable admin core from skunkBOX.
- Make domain-specific features additive rather than embedded in the template.

