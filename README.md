# ChatGPT Morning Brief

A modular, source-transparent toolkit for collecting publicly available macroeconomic data, economic-calendar events, Treasury yields, and public situation-report metadata.

This repository contains general-purpose code and documentation only. It must not contain personal data, private prompts, credentials, API tokens, cookies, private logs, or user-specific account configuration.

## Project principles

- Prefer official primary sources and clearly label secondary sources.
- Preserve observation periods, publication timestamps, time zones, source URLs, and collection timestamps.
- Distinguish missing, unverified, revised, and conflicting data; never replace unknown values with zero.
- Keep collectors modular and independently testable.
- Do not publish full copyrighted articles or reports; retain source links and permitted metadata.
- Respect source terms of use, rate limits, robots directives, and access controls.
- No scheduled workflow is enabled by default. Initial development and tests are manual.

## Planned modules

- China macroeconomic releases
- U.S. macroeconomic releases
- China and U.S. economic/policy calendars
- U.S. Treasury 2-year, 10-year, and 30-year yields
- Public ISW/CTP report metadata tracking
- Data validation and normalized JSON output

## Development status

Repository initialized with project documentation and safe defaults. Collectors and automated workflows have not yet been added.

## Security

Never commit secrets. Use environment variables or a dedicated secret manager for credentials if a future source genuinely requires authentication. Keep real local configuration, logs, and generated output out of version control.

See [docs/architecture.md](docs/architecture.md) and [docs/data_dictionary.md](docs/data_dictionary.md).
