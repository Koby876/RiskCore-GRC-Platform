# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.5.x | ✅ Active |
| < 1.5  | ❌ No longer supported |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report security issues privately by emailing the maintainer directly.
Include as much detail as possible:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if known)

You will receive a response within 72 hours.

## Security Design

- Passwords hashed with bcrypt (cost factor 12)
- API keys encrypted with AES-256 (Fernet)
- All SQL queries use parameterised statements (no SQL injection)
- No network calls except explicit Anthropic API requests
- No telemetry, analytics, or remote logging
- Diagnostic bundle export scrubs all credentials before inclusion
