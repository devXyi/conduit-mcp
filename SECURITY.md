# Security Policy

## Security model

Conduit has two distinct trust boundaries:

1. **Caller boundary** — remote HTTP callers must authenticate with an OAuth access token when HTTP authentication is enabled.
2. **Content boundary** — workspace files and external GitHub content remain untrusted data even after the caller is authenticated.

Conduit is an OAuth resource server. It does not issue user credentials.

## Current controls

- JWT signature validation through issuer JWKS
- issuer and audience validation
- `exp` / `nbf` validation
- signing-key (`kid`) selection
- required-scope enforcement
- workspace path sandboxing
- protection against absolute-path and traversal escapes
- explicit untrusted-content handling
- bounded in-memory event storage for resumability
- server-side Auth0 Management API credentials kept out of remote clients

## Known limitations

- The current event store is process-local and is not suitable for multi-instance horizontal scaling without shared state.
- Workspace indexing can become expensive for very large workspaces.
- Prompt-injection defenses reduce accidental instruction following but cannot make arbitrary external text safe for a model.
- The current remote capability model uses a coarse `conduit:read` scope; finer-grained capabilities are planned.

## Secret handling

Never commit or publish:

- Auth0 client secrets
- Auth0 Management API tokens
- GitHub personal access tokens
- OAuth access tokens
- Authorization headers

Use environment variables or deployment secret stores.

## Reporting a vulnerability

Please report security vulnerabilities privately to the repository owner rather than opening a public issue with exploit details.

Include:

- affected component
- reproduction steps
- security impact
- suggested mitigation, if known

Do not include live credentials in a report.
