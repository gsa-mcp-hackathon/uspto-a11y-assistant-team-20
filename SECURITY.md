# Security Policy

As a U.S. Government agency, the General Services Administration (GSA) takes seriously our responsibility to protect the public's information, including financial and personal information, from unwarranted disclosure.

Software developed by the U.S. General Services Administration (GSA) is subject to the GSA Vulnerability Disclosure Policy.

Please consult our policy for:

How to submit a report if you believe you have discovered a vulnerability.
GSA's coordinated disclosure policy.
Information on how you may conduct security research on GSA developed software and systems.
Important legal and policy guidelines.

## Supported Versions

Use this section to tell people about which versions of your project are
currently being supported with security updates.

| Version (Branch) | Supported          |
| ------- | ------------------ |
| main   | :white_check_mark: |
| other  | :x:

## Security Researchers

Security researchers shall:

- Make every effort to avoid privacy violations, degradation of user experience, disruption to production systems, and destruction or manipulation of data.
- Only use exploits to the extent necessary to confirm a vulnerability. Do not use an exploit to compromise or exfiltrate data, establish command line access and/or persistence, or use the exploit to "pivot" to other systems. Once you've established that a vulnerability exists, or encountered any of the sensitive data outlined above, you must stop your test and notify us immediately.
- Keep confidential any information about discovered vulnerabilities for up to 90 calendar days after you have notified GSA. For details, please review Coordinated Disclosure.

## Hackathon note

MCP servers built from this template expose their `/mcp` endpoint **without authentication** by default (matching the public-data pilot posture). This is acceptable for a hackathon over public data. Before any non-hackathon use, front the endpoint with authentication and review your agency's ATO requirements. Never commit secrets — keep API keys in environment variables / `.env` (git-ignored), not in source.

This server's whole job is fetching **caller-supplied** URLs (an agent, possibly
relaying an untrusted user's request), not one fixed operator-controlled API — a
materially different threat model than the hackathon template's default "reject
any path that tries to escape a fixed origin" pattern. `utils.fetch_url_safely`
(used by both `scan_page_alt_text` and `fetch_image`) instead: allowlists the
`http`/`https` schemes, resolves the hostname and rejects any address in a
loopback/private/link-local/multicast/reserved/CGNAT range (this also covers the
cloud metadata endpoint, `169.254.169.254`), disables automatic redirects and
re-validates every redirect hop the same way, disables environment proxies, caps
the response size, and sanitizes upstream failures before returning them.

**Named residual risk — DNS rebinding:** the pre-connect resolve check and the
actual HTTP connection are two separate steps, so an attacker controlling DNS for
their own domain could in principle return a safe IP for the check and a
blocked one for the connection. A full fix needs a connect-time socket hook that
pins the validated IP; this is out of scope for the hackathon pass and is
reflected as a comment on `_assert_host_resolves_safely` in `utils.py`, not
silently assumed away.

Treat all tool arguments, retrieved content, and agent-to-agent messages as
untrusted. Do not include upstream response bodies, headers, full URLs, query
strings, stack traces, credentials, names, SSNs, dates of birth, addresses, or other
sensitive values in MCP errors or logs. Use structured logs with explicitly
allowlisted fields and define retention and access controls before processing PII.
