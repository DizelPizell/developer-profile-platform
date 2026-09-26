\# Developer Profile Platform



\## Project



Developer Professional Profile Platform.



Core principle:



> Не рассказывай, что ты умеешь. Покажи.



The platform allows developers to create professional profiles backed by real projects, GitHub evidence, live demos, architecture and technical information.



V1 is NOT a LinkedIn or HeadHunter clone.



V1 focuses on:

\- developer profiles

\- projects

\- featured projects

\- public profiles

\- GitHub integration

\- live demos

\- technical project workspace

\- analytics



Recruiter search, vacancies, matching and messaging are V2.



\---



\## Product principle



We do not assign artificial developer scores or rankings.



Evidence is more important than scores.



Do not invent:

\- skill scores

\- developer ratings

\- contribution percentages

\- quality scores

\- arbitrary rankings



GitHub data and developer-provided context must remain distinguishable.



\---



\## Architecture



Architecture style:



Modular monolith.



Backend:

\- Python

\- FastAPI

\- SQLAlchemy 2

\- PostgreSQL

\- Alembic

\- pytest



Frontend:

\- Next.js

\- TypeScript

\- Tailwind CSS

\- shadcn/ui

\- Vitest

\- React Testing Library

\- Playwright



Infrastructure:

\- Docker

\- Docker Compose

\- GitHub Actions

\- Nginx



Storage:

\- S3-compatible object storage

\- MinIO locally



External integration:

\- GitHub API



Redis, Kafka and Kubernetes are NOT part of V1 unless a concrete requirement appears.



Do not introduce new infrastructure technologies without explaining the problem they solve.



\---



\## Backend architecture



Use a modular monolith.



Logical flow:



HTTP

↓

API / Controller

↓

Application / Use Case

↓

Domain

↓

Repository

↓

Infrastructure



Do not over-engineer Clean Architecture.



Avoid unnecessary abstractions and interfaces.



Do not create abstractions only for theoretical purity.



\---



\## Domain contexts



Main bounded contexts:



\- Identity

\- Profile

\- Projects

\- GitHub

\- Analytics

\- Files



Main aggregate roots:



\- User

\- Profile

\- Project

\- Analytics



\---



\## Important business rules



\### Profile



Each User has exactly one Profile.



Profile has a unique public slug.



Profile lifecycle:



PRIVATE

PUBLISHED

UNPUBLISHED



\### Project



Project lifecycle:



DRAFT

READY

PUBLISHED

ARCHIVED



A Project does not require GitHub.



A Project does not require a Demo.



Projects may represent:

\- commercial work

\- freelance work

\- educational projects

\- open-source projects

\- NDA work



\### Featured projects



A profile can have a maximum of 3 featured projects.



This is a backend business invariant, not only a frontend limitation.



\### GitHub



GitHub is the source of truth for technical repository data.



Developer is the source of truth for:

\- role

\- contribution

\- business context

\- problem

\- results

\- screenshots

\- demo URL



Never infer contribution percentages from commits.



Never calculate artificial skill scores from GitHub activity.



GitHub repository import is NOT the same thing as a Project.



Import creates an imported project which the developer can enrich with context.



GitHub sync must be idempotent.



GitHub tokens must never be stored as plaintext.



\---



\## API



API prefix:



`/api/v1`



API style:



REST.



JSON request/response bodies.



Use explicit DTOs.



Never expose database entities directly through public endpoints.



Public DTOs must be whitelisted.



Never expose:

\- password hashes

\- session secrets

\- GitHub access tokens

\- private settings

\- internal database fields



Error format:



```json

{

&#x20; "error": {

&#x20;   "code": "VALIDATION\_ERROR",

&#x20;   "message": "Invalid request",

&#x20;   "details": {},

&#x20;   "request\_id": "uuid"

&#x20; }

}

API contract is defined in:



/docs/api/



OpenAPI is the source of truth for the API contract.



Do not silently change API behavior without updating the contract.



Database



PostgreSQL is the primary database.



Use SQLAlchemy 2.



Use Alembic migrations.



Do not modify production schema manually.



Every schema change must have a migration.



Security



Authentication:



HTTP-only cookies

Secure cookies in production

SameSite policy

CSRF protection

GitHub OAuth



Authorization must be checked on the backend.



Never trust frontend authorization.



Every resource owned by a user must have an ownership check.



Never log secrets or access tokens.



Validate all external input.



Analytics



Analytics is a non-critical subsystem.



If analytics fails, the main user operation must continue.



Never block navigation because analytics failed.



Do not make analytics unnecessarily invasive.



Development workflow



Before implementing a non-trivial feature:



Understand the requirement.

Check existing architecture.

Check API contract.

Check database model.

Identify affected domains.

Propose implementation plan.

Explain important trade-offs.

Wait for approval when the decision is architectural or irreversible.

Implement.

Add tests.

Run validation.

Review the diff.

Update documentation if necessary.

How Claude should work



Do NOT immediately generate code for a large task.



First analyze.



For non-trivial tasks provide:



Understanding



What you understand from the requirement.



Impact



Which parts of the system are affected.



Plan



Concrete implementation steps.



Risks



Potential problems or trade-offs.



Decision



What approach you recommend and why.



Then implement after approval.



For small, obvious tasks implementation can proceed directly.



Challenge the developer



Do not blindly agree with the developer.



If a proposed solution is:



over-engineered

insecure

inconsistent with architecture

unnecessarily expensive

difficult to maintain

premature

solving a problem that does not exist



say so clearly.



Explain the alternative.



The goal is not to make the developer feel correct.



The goal is to build a maintainable production-oriented system.



Teaching mode



The developer is using this project to learn software engineering and Tech Lead practices.



When making important decisions, explain:



why the decision is needed

what alternatives exist

why one option is preferred

what trade-offs exist

what would change the decision later



Do not explain every trivial line of code.



Focus explanations on engineering decisions.



Git



Use Conventional Commits.



Examples:



feat(auth): add user registration



fix(profile): validate public slug



test(auth): add registration tests



docs(api): update profile contract



Do not create meaningless commits.



Keep commits focused and logically grouped.



Quality



Definition of Done:



implementation complete

validation implemented

tests added

error handling implemented

security considered

documentation updated when required

lint passes

tests pass

API contract remains consistent

migration exists for schema changes

code has been reviewed



"Works on my machine" is not Definition of Done.



Current development stage



The repository is currently in the bootstrap stage.



Completed:



repository initialized

project directory structure created

Git initialized

PostgreSQL 17 running through Docker Compose

initial infrastructure commit created



Current next goal:



Build the minimal FastAPI backend skeleton and connect it to PostgreSQL.



Do not implement business logic yet.



Documentation



Important documentation:



/docs/product/

/docs/architecture/

/docs/api/

/docs/adr/



Read relevant documentation before making architectural changes.



If documentation conflicts with the code, identify the conflict instead of silently choosing one.



Important rule



Do not turn V1 into a distributed system.



Prefer:



simple

explicit

testable

maintainable



over:



complex

abstract

distributed

prematurely scalable

