# Definition of Done

A feature is not Done because it works locally.

## Functional
- requirements understood
- business rules implemented
- validation implemented
- expected errors handled
- ownership/privacy checked

## Code quality
- follows project structure
- no unnecessary abstraction
- no duplicated business logic
- clear naming
- no hardcoded secrets

## Tests
- unit tests for important business rules
- integration tests for relevant API/database behavior
- E2E test for important user flows when applicable

## API
- request schema defined
- response schema defined
- correct HTTP status codes
- OpenAPI updated

## Security
- authentication checked
- authorization checked
- sensitive data protected
- no secrets in logs
- CSRF handled where applicable

## Documentation
- docs updated when behavior/architecture changes
- ADR added for significant architectural decisions

## Git
- changes logically grouped
- Conventional Commit
- reviewable history

## Review questions
1. What could break?
2. What happens with invalid input?
3. Can another user access this resource?
4. What happens if an external service fails?
5. Does this add unnecessary infrastructure?
6. Is the decision documented?
