# Source smoke tests

These are read-only smoke tests for three public data sources:

1. National Bureau of Statistics of China (NBS) public data platform, via the upstream `nbs_fetcher` package.
2. Federal Reserve Bank of St. Louis FRED public CSV endpoint (DGS2, DGS10, DGS30).
3. U.S. Treasury daily Treasury par yield curve XML endpoint.

## Run in GitHub's cloud (recommended)

1. Open the repository's **Actions** tab.
2. Select **Manual public data source tests** in the workflow list.
3. Click **Run workflow**, keep the `main` branch selected, then click the green **Run workflow** button.
4. Open the completed run and download the artifact named `public-data-source-test-results`.

This workflow has only the `workflow_dispatch` trigger. It does not run on a schedule, on pushes, or on pull requests. It requests read-only repository permissions, does not use secrets, and does not commit test output.

## Results

Each run writes one JSON result per source plus `summary.json` under `tests/output/`. Each result contains:
- success/failure status and collection timestamp;
- the source URL and direct request URL;
- the latest observation/data date found;
- parsed records and/or the raw source response;
- an error message when a request or validation fails.

GitHub Actions uploads these files as a workflow artifact for 14 days. Runtime output is intentionally ignored by Git and is not committed to the repository.

## Local Windows execution (optional)

If a developer later wants to run the tests locally, the commands are:

```powershell
py -3 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r tests\\requirements.txt
python tests\\run_smoke_tests.py
```

For the optional NBS browser-session bootstrap, install Playwright and Chromium, then set `NBS_AUTO_SESSION=1`. The cloud workflow does this automatically. It does not bypass login, CAPTCHA, or access controls; if the public site still rejects the request, the test records failure.

## Scope and safety

- Tests run sequentially with bounded request timeouts.
- No API keys or credentials are required or stored.
- TLS certificate verification is enabled in the test code.
- No scheduled workflow is configured.
- NBS catalogue traversal is bounded and seeks a CPI-related monthly indicator; if the live catalogue changes, the NBS test may fail and preserve the raw catalogue/error for diagnosis.
