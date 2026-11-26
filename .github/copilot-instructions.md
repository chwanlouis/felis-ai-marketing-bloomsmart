# GitHub Copilot Repository Instructions

## Core Architectural Constraints

### Container Backend & Base Class Rule
- **Inheritance Lock**: All classes representing container components or backend services **must inherit from `BaseClass`**. 
- **Immutability**: The design, signature, and existence of `BaseClass` **cannot be modified, refactored, or removed**. 
- Any newly implemented container backend service, worker, or core handler must strictly adhere to this inheritance pattern without bypassing `BaseClass`.

## Tech Stack & Standards
- **Language**: Python 3.11+
- **Database**: PostgreSQL 15+ (using precise numeric types for financial and inventory data)
- **Type Safety**: Full type annotations required for all functions, methods, and class attributes.