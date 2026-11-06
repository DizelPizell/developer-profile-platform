# ADR-020: Developer Contacts

## Status

Accepted. The legal questions are not decided: they require a lawyer's review before the launch (step 9.8; see "Visibility and personal data").

Amends ADR-013-profile-editing-and-origin-check.md: `PATCH /profile` and both profile responses gain `contacts`, and the rule "never email" of the public DTO now means `users.email`.

## Context

V1 includes minimal contacts, so that a visitor can contact the developer (PRD, "V1 scope"; US-025). DEVELOPMENT_PLAN left open which contacts there are, where they are shown and what "contact visibility" means. No model, contract or mockup exists yet.

The public profile is rendered on the server and is reachable without a session, and its JSON endpoint is open to anyone. A value placed in either is available to scrapers and to the caches of search engines. Email and phone are the values people least want collected in bulk.

Contacts are the first free-form links on a public page. Until now every link there went to a host the platform knows (`github.com`, ADR-019).

## Decision

### The set of contacts

- One each of `EMAIL`, `TELEGRAM`, `LINKEDIN` and `PHONE`.
- Up to 3 of `OTHER`: a name and an `http` or `https` link. The button in the cabinet is «Другие способы связи».
- At most 7 positions in all.
- All are optional. This ADR does not change what a profile needs for publication (ADR-013).

### Model

Contacts belong to the Profile aggregate. Table `profile_contacts`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `profile_id` | UUID | FK → `profiles`, `ON DELETE CASCADE` |
| `type` | text | `EMAIL`, `TELEGRAM`, `LINKEDIN`, `PHONE` or `OTHER` |
| `value` | text | The normalized value (see "Validation") |
| `label` | text, nullable | The name of an `OTHER` contact |
| `position` | smallint | 1..7, the order in the list |
| `created_at` | timestamp | |

Constraints:

- CHECK on `type`.
- A partial unique index on `(profile_id, type)` where `type <> 'OTHER'`: one standard contact of each type.
- `label` is required for `OTHER` and is `NULL` for the other types, by a CHECK.
- `UNIQUE (profile_id, position)` and `position BETWEEN 1 AND 7`, which cap a profile at 7 rows, as the position range caps a project's technologies (ADR-015).
- CHECKs on length: `value` by type (see "Validation"), `label` up to 40, neither blank.

The limit of 3 `OTHER` contacts is a domain rule. The database holds the cap of 7 but not the 3.

Alternatives are under "Alternatives considered".

### Writing

- `contacts` is an optional field of `PATCH /profile`. Absent keeps the list, a list replaces it whole, `[]` clears it, `null` is rejected: the rules of `technologies` (ADR-015).
- An item is `{type, value, label}`. `label` is sent only for `OTHER`. The server sets `position` from the order of the list.
- The route keeps its `SELECT ... FOR UPDATE` on the profile row, so two saves cannot interleave.
- The replacement runs an explicit `DELETE` before the `INSERT`, in one transaction. Left to the unit of work, the inserts could run first and break `UNIQUE (profile_id, position)`.
- `profiles.updated_at` changes only when the normalized list differs from the stored one (ADR-013).

### Validation

For the standard types the server stores a normalized value and builds the link itself. A URL sent by the user is never kept for them, so a stored standard contact cannot point anywhere else. No new dependencies: email and phone are parsed by the platform's own code.

| Type | Accepted input | Stored in `value` | Limit | Link built by the server | Rejected |
|---|---|---|---|---|---|
| `EMAIL` | ASCII address, matching `^[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$` | The address with the domain in lower case | 254 | `mailto:{value}` | `?`, `&`, `%`, spaces, Cyrillic domains and any other non-ASCII |
| `TELEGRAM` | `name`, `@name`, `t.me/name`, `https://t.me/name`, with an optional trailing slash | `name`, in the spelling entered | 5–32 | `https://t.me/{name}` | Other hosts, invite links (`t.me/+…`, `t.me/joinchat/…`), deeper paths, query strings, Telegram's reserved paths |
| `LINKEDIN` | `linkedin.com/in/{slug}` with `https://`, `www.` or a regional subdomain, and an optional trailing slash | `slug` | 3–100 | `https://www.linkedin.com/in/{slug}` | Other hosts compared exactly, not by suffix (`linkedin.com.evil.example`, `linkedin.com@evil.example`), `/company/` and other paths, query strings |
| `PHONE` | `+` and digits; spaces, hyphens and parentheses are removed | E.164, matching `^\+[1-9]\d{7,14}$` (8–15 digits) | 16 | `tel:{value}` | A number without `+`. `8…` is not rewritten to `+7…` |
| `OTHER` | An `http` or `https` URL with a host that has a dot; a name as plain text | The URL with the scheme in lower case; the name in `label` | URL 2048, name 40 | The stored URL | Any other scheme (`javascript:`, `data:`), a login in the URL, control characters, whitespace, a backslash |

- Every value is trimmed. A blank `value` is an error, not a removed contact: the form leaves empty rows out of the list.
- `label` goes through `plain_text` (ADR-013) and is rendered as text.
- The server never requests these URLs: no previews and no checks. There is no SSRF surface.
- Errors follow the existing shape: `loc` `["body", "contacts", <index>, "value"]` or `"label"`, and `["body", "contacts"]` for a repeated type or too many items. Input values are never echoed (ADR-013).

#### What the external rules say

Checked in the official documentation on 2026-11-06.

| Service | Confirmed | Source |
|---|---|---|
| Telegram | Usernames use `A-z` (case-insensitive), `0-9` and underscores; 5–32 characters | https://core.telegram.org/method/account.checkUsername, https://telegram.org/faq |
| Telegram | Public links are `t.me/<username>`. `t.me/+<hash>` and `t.me/joinchat/<hash>` are invite links, `t.me/+<phone_number>` resolves a phone number, and paths such as `addstickers`, `boost`, `invoice`, `share`, `login`, `proxy`, `socks`, `c` and `nft` are not usernames | https://core.telegram.org/api/links |
| LinkedIn | A custom URL is 3–100 characters, case-insensitive, without spaces, symbols, special characters or the word LinkedIn | https://www.linkedin.com/help/linkedin/answer/a542685 |

Assumptions to check before C.1. The documentation above does not settle them:

- **Telegram**: whether a username may start with a digit or an underscore, or hold repeated or trailing underscores. C.1 accepts what the confirmed rule allows and does not add stricter rules on a guess.
- **Telegram**: the complete list of reserved paths, to be copied from the page above when C.1 starts.
- **LinkedIn**: the allowed characters are not listed. The slug is assumed to be `^[A-Za-z0-9-]{3,100}$`, hyphens included, because generated profile addresses are assumed to use them.
- **LinkedIn**: the help page does not show the `/in/` path. `https://www.linkedin.com/in/{slug}` is the owner's decision and an assumption about the service.
- **LinkedIn**: addresses in non-Latin scripts are rejected by the assumed pattern. Whether real profiles have them is not confirmed.

### Threats

| Threat | Countermeasure |
|---|---|
| Domain substitution in a standard contact (`linkedin.com.evil.example`, `linkedin.com@evil.example`) | Hosts are compared exactly; only the name or slug is stored; the server builds the link |
| `javascript:` or `data:` in a link | `OTHER` allows only `http` and `https`, on the server. The frontend repeats the check per type, as `isGitHubUrl` does, and a link that fails it stays plain text |
| `mailto:` injection (`a@b.c?bcc=x`) | The address pattern has no `?`, `&` or `%`, so the link needs no escaping and cannot carry parameters |
| Bulk collection of email and phone | Their values are in neither the server HTML nor the public profile JSON. They come from a separate endpoint on a click (see "Visibility and personal data"), with a rate limit from step 8.3 |
| Leak through props | The client component receives no value. A prop of a client component is serialized into the HTML, which would undo the point. It fetches the value on a click |
| A misleading name (`OTHER` labelled «GitHub» leading elsewhere) | The host is shown next to the name, read with `new URL`, so an internationalized host appears in punycode. The name is the developer's text and carries «От автора» |
| Open redirect | The platform has no redirector: links go straight to the target |
| Link spam for search ranking | `rel` includes `nofollow ugc` |
| Tabnabbing and referrer leaks | `target="_blank"` with `rel="noopener noreferrer nofollow ugc"`. `tel:` and `mailto:` have no `target` |
| Markup in a name or value | Rendered as React text, never as HTML |
| Values in logs | Request bodies are not logged, error responses do not echo input, and frontend log lines name fields only |

### Visibility and personal data

- **Public**: `TELEGRAM`, `LINKEDIN` and `OTHER`, with `value` and `url`, in `PublicProfileResponse`. They are in the server HTML.
- **On request**: `EMAIL` and `PHONE` are listed in `PublicProfileResponse` with `value` and `url` equal to `null`, so the page knows they exist. The value comes from `GET /public/profiles/{slug}/contacts?type=EMAIL|PHONE`.
- Without JavaScript email and phone are not visible. This is accepted.
- **No visibility switch in V1.** "Contact visibility" (PRD) means that the developer adds or removes a contact, and that contacts follow the profile's state. Nothing else reads a stored contact in V1, so a hidden one would be personal data kept for no reader. A nullable or defaulted column can add a switch later.
- **`PRIVATE` profile**: contacts can be edited; publicly the profile and the new endpoint answer 404.
- **`PUBLISHED` profile**: a saved contact is public at once. There is no draft, so the form says so.
- **`users.email`** comes from GitHub (ADR-012). It is never published and never fills in a contact. A contact's email is a separate value that the developer enters.
- Deleting a contact removes the row. Deleting a user removes contacts by cascade.

Requires a lawyer's review before the launch (9.8). This ADR states no legal conclusions:

- whether publishing a phone or an email needs a consent, in what form, and whether a checkbox and its date must be stored;
- what the personal data policy must say and where it is published;
- how a person can demand that distribution stops, and whether removing a contact and hiding the profile are enough;
- who the operator is;
- whether localization requirements apply to the hosting chosen in 9.1 and 9.3;
- what to do about a contact that belongs to someone else.

These questions do not block C.1. If a consent must be stored, it is added by a later migration. Steps 9.7 and 9.8 carry them.

### API and contract

| Change | Compatibility |
|---|---|
| `ProfileUpdate.contacts`: optional | Existing clients are unaffected |
| `OwnProfileResponse.contacts`: required list of `{type, value, label, url}` | The current frontend ignores it |
| `PublicProfileResponse.contacts`: required list of `{type, value, label, url}`, `value` and `url` `null` for `EMAIL` and `PHONE` | The current frontend drops unknown fields |
| `GET /public/profiles/{slug}/contacts?type=EMAIL\|PHONE` → `{type, value, url}` | New |

- `url` is what the server built; for `OTHER` it equals `value`.
- The new endpoint needs no session. It returns only the requested value, with `Cache-Control: no-store`.
- A private, missing or malformed profile, or a profile without that contact, gives the same 404 as `GET /public/profiles/{slug}`. A `type` other than `EMAIL` or `PHONE` gives 422 `VALIDATION_ERROR`.
- `PUT` is not used: CORS allows `GET`, `POST`, `PATCH`, `DELETE` and `OPTIONS` (ADR-013, ADR-015).
- The public profile takes one more query for any number of contacts.

C.1 must keep the Redocly baseline of `docs/api/openapi.yaml` (`@redocly/cli@1.34.0`): 3 errors and 36 warnings. The new operation needs an `operationId`, `security: []` and its 404 response, or the warnings grow.

### Frontend

- A section «Контакты» on the public page, marked «От автора», with a hero button that links to it. Without contacts neither is rendered. Its place on the page comes from the mockup.
- `TELEGRAM`, `LINKEDIN` and `OTHER` are server rendered. `OTHER` shows the name and the host.
- «Показать email» and «Показать телефон» are one small client component. It requests the value only on a click and has idle, loading, shown and error states. It gets the type and the slug, never the value.
- In the cabinet the block sits in the profile form and saves with «Сохранить»: four fixed fields, then the rows of «Другие способы связи» (name, link, remove). At the limit the button is disabled with a hint. A hint says that contacts are visible to everyone while the profile is published.
- The form sends the whole list when it changed and shows the normalized values from the response.
- `profileFieldErrors` reads only `loc` of length 2 today and must learn the paths of contacts.
- The public reader follows F-GH2: a missing `contacts` is `[]` without a log; a wrong shape is `[]` with one log line per profile, naming the field and no values. The rest of the profile keeps working.
- No Contacts mockup exists. C.2 starts after it is drawn.

## Consequences

### Positive

- A visitor can reach the developer from the public page.
- A standard contact can only lead to the service it names.
- Email and phone stay out of page HTML, public JSON and the caches of search engines.
- One table and one write path serve all types; adding a type is a CHECK and a validator.

### Negative

- Without JavaScript email and phone are not reachable.
- Until step 8.3 the new endpoint has no rate limit, so a script can read contact values one profile at a time. A bot that runs JavaScript can do the same after 8.3, more slowly. The measure reduces bulk collection; it does not prevent it.
- The public response reveals that an email or a phone exists.
- Addresses with Cyrillic domains and numbers without `+` are rejected.
- The limit of 3 `OTHER` contacts rests on the domain layer alone.
- The form gets a list and row errors, more than a set of plain fields.

## Alternatives considered

- **Columns on `profiles` for the four types, plus a table for `OTHER`**: rejected — the list and its errors would be needed anyway, so there would be two mechanisms.
- **A JSON column on `profiles`**: rejected — the database could not hold the rules, and ADR-013 repeats invariants there.
- **All values in the public JSON and HTML**: rejected — anyone can read them in bulk.
- **Obfuscation in the HTML**: rejected — it hurts accessibility and does nothing while the JSON is open.
- **`email-validator` and `phonenumbers`**: rejected — dependencies for two fields, and the strict ASCII pattern also closes the `mailto:` injection.
- **A separate `PUT /profile/contacts`**: rejected — `PUT` is not in CORS, and the form has one save.
- **A visibility switch per contact**: rejected for V1, see "Visibility and personal data".

## Open questions

- The legal questions listed under "Visibility and personal data" (9.7, 9.8).
- The assumptions about Telegram and LinkedIn, before C.1.
- The place of the section on the public page, in the mockup.

## Not included

- `CONTACT_CLICK` and any contact analytics (V1.1, Phase 7).
- A visibility switch per contact.
- A consent in the model.
- The rate limit itself (step 8.3).
- A redirector or link previews.
