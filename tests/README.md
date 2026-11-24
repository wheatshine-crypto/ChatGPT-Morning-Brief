# Source smoke tests

These are manual, read-only smoke tests for three public data sources. They do not create scheduled jobs, GitHub Actions, database writes, or changes to any other repository.

## Sources tested

1. National Bureau of Statistics of China (NBS) public data platform, via the upstream `nbs_fetcher` package.
2. Federal Reserve Bank of St. Louis FRED public CSV endpoint (DGS2, DGS10, DGS30).
3. U.S. Treasury daily Treasury par yield curve XML endpoint.

Each run writes one JSON result per source plus `summary.json` under `tests/output/`. Each result contains:
- success/failure status and collection timestamp;
- the source URL and direct request URL;
- the latest observation/data date found;
- parsed records and/or the raw source response;
- an error message when a request or validation fails.

Generated output is intentionally ignored by Git and stays on the machine running the test. Do not commit runtime output.

## Windows PowerShell

From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r tests\requirements.txt
python tests\run_smoke_tests.py
```

If PowerShell blocks virtual-environment activation, run the Python executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tests\requirements.txt
.\.venv\Scripts\python.exe tests\run_smoke_tests.py
```

## NBS browser session (optional)

The NBS website may return a JavaScript challenge to direct HTTP requests. The test always keeps TLS certificate verification enabled. By default it does not launch a browser. If the NBS request reports a challenge, install the optional browser dependency and Chromium:

```powershell
python -m pip install "playwright>=1.44"
python -m playwright install chromium
$env:NBS_AUTO_SESSION = "1"
python tests\run_smoke_tests.py
```

This option uses the upstream package's browser-session bootstrap for the public page; it does not bypass login, CAPTCHA, or access controls. If the site still rejects the request, the test records failure rather than attempting workarounds.

## Scope and safety

- Requests are sequential, with a small number of source requests and bounded timeouts.
- No API keys or credentials are required or stored.
- TLS verification is enabled.
- No GitHub Actions or scheduler is configured.
- NBS traversal is bounded and seeks a CPI-related monthly indicator; if the live catalogue changes, the NBS test may fail and preserve the raw catalogue/error for diagnosis.
