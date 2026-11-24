# Architecture

## Purpose

This project collects and normalizes publicly available information. Collectors retrieve source material and metadata; validators check structure and provenance. Editorial interpretation belongs to a separate reporting layer.

## Components

- `collectors/`: independent source-specific collectors.
- `validators/`: schema, time-window, unit, duplicate, and provenance checks.
- `config/`: sanitized public source definitions and examples only.
- `tests/`: deterministic tests using synthetic or otherwise redistributable fixtures.
- `output/` and `logs/`: local runtime artifacts; excluded from version control.

## Data flow

1. Load source definitions.
2. Retrieve public pages, feeds, or documented public APIs.
3. Preserve source URL and verifiable publication time.
4. Normalize records into the shared schema.
5. Validate units, observation periods, timestamps, source tier, and status.
6. Emit structured records; flag uncertainty rather than guessing.
7. Review results against primary sources before downstream use.

## Time handling

- Store timestamps in ISO 8601 format with an explicit UTC offset or timezone.
- Keep source publication time separate from collection time.
- For a report dated D in Asia/Shanghai, the standard news window is D-1 07:00 inclusive to D 07:00 exclusive.
- A 15-day forward calendar covers report date D and the following 14 calendar days.
- Do not infer an event time when the source publishes only a date.

## Source hierarchy

1. Official primary release or institution calendar.
2. Official statistical or market-data distribution service.
3. Reputable secondary reporting for discovery and cross-checking.

Aggregators are not automatically equivalent to the original publishing institution.

## Safety and publishing boundary

- No hard-coded secrets or personal credentials.
- Do not log authorization headers, cookies, or secret values.
- Do not commit personal information, private prompts, account data, or private runtime logs.
- Publish only generic code, sanitized configuration examples, documentation, and safe test fixtures.
- Do not scrape behind authentication or bypass technical access restrictions.
- Respect copyright and source terms; metadata and links do not grant permission to republish full source content.

## Current status

Documentation scaffold only. No collectors, schedulers, or GitHub Actions have been implemented.
