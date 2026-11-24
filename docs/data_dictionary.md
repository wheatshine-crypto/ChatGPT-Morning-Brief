# Data Dictionary

Records should be UTF-8 JSON. Unknown values must be represented as `null`, not guessed or replaced with zero.

| Field | Type | Meaning |
|---|---|---|
| `record_type` | string | `macro_indicator`, `calendar_event`, `treasury_yield`, or `report` |
| `name` | string | Indicator, event, or report name |
| `value` | number/string/null | Numeric value or concise event description |
| `unit` | string/null | Unit, such as percent, basis points, USD, or persons |
| `observation_period` | string/null | Period measured, such as month or quarter |
| `event_date` | string/null | Event or release date |
| `published_at` | string/null | Verifiable original publication timestamp |
| `published_timezone` | string/null | Source timezone or explicit offset |
| `collected_at` | string | Collection timestamp with timezone |
| `source_name` | string | Publishing institution or outlet |
| `source_url` | string | Direct source URL |
| `source_tier` | string | `official_primary`, `official_calendar`, or `secondary` |
| `status` | string | `verified`, `unverified`, `missing`, or `conflict` |
| `notes` | string/null | Definitions, revisions, conflicts, or caveats |

## Validation rules

1. Preserve observation period and publication date separately.
2. Distinguish percent, percentage points, and basis points.
3. Calculate yield changes only when comparable observations from the same defined source are available.
4. Calendar events must carry timezone information when the source provides it; unknown event times remain unknown.
5. For reports, distinguish the report's nominal date from its actual publication timestamp.
6. Preserve revisions and avoid silently overwriting historical observations.
7. `verified` means the record has passed the project's source and field checks; it is not an endorsement of the source's analysis.
