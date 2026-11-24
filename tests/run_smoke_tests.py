#!/usr/bin/env python3
"""Manual read-only smoke tests for NBS, FRED, and U.S. Treasury."""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import traceback
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
TIMEOUT_SECONDS = 30
HEADERS = {
    "User-Agent": "ChatGPT-Morning-Brief-source-smoke-test/0.1 (manual public-data validation)",
    "Accept": "*/*",
}
FRED_SOURCE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TREASURY_SOURCE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?type=daily_treasury_yield_curve"
)
TREASURY_XML_BASE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
)
NBS_SOURCE_URL = "https://data.stats.gov.cn/dg/website/page.html#/pc/national/monthData"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def json_safe(value: Any) -> Any:
    """Convert package-returned objects into JSON-serializable values."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def save_result(name: str, result: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"{name}.json"
    path.write_text(
        json.dumps(json_safe(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def base_result(source_name: str, source_url: str) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "status": "failed",
        "success": False,
        "collected_at": now_iso(),
        "data_date": None,
        "source_url": source_url,
        "request_url": None,
        "raw_data": None,
        "parsed_data": None,
        "error": None,
    }


def finish_error(result: dict[str, Any], exc: BaseException) -> dict[str, Any]:
    result["status"] = "failed"
    result["success"] = False
    result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def run_nbs() -> dict[str, Any]:
    result = base_result("National Bureau of Statistics of China - National Data", NBS_SOURCE_URL)
    result["tls_verification"] = True
    result["auto_browser_session"] = os.getenv("NBS_AUTO_SESSION", "0").lower() in {
        "1", "true", "yes"
    }
    try:
        from nbs_fetcher import NBSFetcher

        # The upstream package defaults verify=False; override it explicitly.
        client = NBSFetcher(
            verify=True,
            timeout=45,
            max_retries=2,
            retry_backoff=1,
            auto_session=result["auto_browser_session"],
        )
        result["request_url"] = (
            "https://data.stats.gov.cn/dg/website/publicrelease/web/external/"
            "new/queryIndexTreeAsync; queryIndicatorsByCid; stream/esData"
        )

        roots = client.tree("monthData")
        if not isinstance(roots, list) or not roots:
            raise RuntimeError("NBS returned an empty monthly-data catalogue.")

        # Traverse the live catalogue breadth-first. The first version stopped
        # after 45 nodes, before reaching the price-indicator branch.
        queue: list[tuple[dict[str, Any], list[str], int]] = [
            (node, [str(node.get("name") or node.get("_name") or "")], 0)
            for node in roots if isinstance(node, dict)
        ]
        visited = 0
        max_nodes = 600
        max_depth = 12
        seen_ids: set[str] = set()
        matching_nodes: list[dict[str, Any]] = []
        candidate = None

        while queue and visited < max_nodes:
            node, path, depth = queue.pop(0)
            node_id = str(node.get("_id") or "")
            if node_id and node_id in seen_ids:
                continue
            if node_id:
                seen_ids.add(node_id)
            visited += 1
            node_name = str(node.get("name") or node.get("_name") or "")
            searchable = " / ".join(path + [node_name]).upper()

            # Query indicator metadata only on potentially relevant branches.
            if any(term in searchable for term in ("价格", "CPI", "居民消费")):
                indicators = client.indicators("monthData", cid=node_id) if node_id else []
                labels = [str(item.get("label", "")) for item in indicators]
                matching_nodes.append({
                    "path": path,
                    "node_id": node_id,
                    "node_name": node_name,
                    "indicator_labels": labels,
                })
                preferred_items = [
                    item for item in indicators
                    if any(term in str(item.get("label", "")).upper()
                           for term in ("居民消费价格", "CPI"))
                ]
                if preferred_items:
                    preferred_items.sort(
                        key=lambda item: (
                            0 if "同比" in str(item.get("label", "")) else 1,
                            0 if "居民消费价格指数" in str(item.get("label", "")) else 1,
                        )
                    )
                    candidate = (node, path, preferred_items[0])
                    break

            if depth < max_depth and node_id and not node.get("isLeaf", False):
                children = client.tree("monthData", pid=node_id)
                for child in children:
                    if isinstance(child, dict):
                        child_name = str(child.get("name") or child.get("_name") or "")
                        queue.append((child, path + [child_name], depth + 1))

        result["catalogue_nodes_checked"] = visited
        result["catalogue_nodes_limit"] = max_nodes
        result["catalogue_matches"] = matching_nodes
        if candidate is None:
            raise RuntimeError(
                "CPI indicator not found in the expanded monthly catalogue scan "
                f"({visited} nodes; limit={max_nodes}). Catalogue matches are preserved."
            )

        node, path, preferred = candidate
        indicator_id = preferred.get("indicator_id")
        if not indicator_id:
            raise RuntimeError("The matched NBS indicator did not include an indicator_id.")

        raw_result = client.fetch(
            "monthData",
            cid=str(node["_id"]),
            series=str(indicator_id),
            sequence="area",
            format="raw",
        )
        responses = raw_result.get("responses", [])
        response_payloads = [
            entry.get("response", {}) for entry in responses if isinstance(entry, dict)
        ]
        periods = []
        records = []
        for payload in response_payloads:
            for period in payload.get("data", []) if isinstance(payload, dict) else []:
                period_code = period.get("code")
                if period_code:
                    periods.append(str(period_code))
                for item in period.get("values", []) or []:
                    records.append({
                        "period_code": period_code,
                        "indicator_label": item.get("i_showname", preferred.get("label")),
                        "area": item.get("area"),
                        "value": item.get("value"),
                        "unit": item.get("du_name", preferred.get("unit")),
                    })

        if not records:
            raise RuntimeError("NBS request completed but returned no CPI observation records.")

        result["data_date"] = max(periods) if periods else None
        result["parsed_data"] = {
            "catalogue_path": path,
            "indicator": preferred,
            "record_count": len(records),
            "records": records,
        }
        result["raw_data"] = {
            "root_catalogue": roots,
            "catalogue_matches": matching_nodes,
            "raw_fetch_response": raw_result,
        }
        result["status"] = "success"
        result["success"] = True
        return result
    except Exception as exc:
        return finish_error(result, exc)


def run_fred() -> dict[str, Any]:
    result = base_result(
        "Federal Reserve Bank of St. Louis - FRED",
        "https://fred.stlouisfed.org/series/DGS2",
    )
    result["request_strategy"] = (
        "One series per CSV request; bounded retries with increasing timeouts."
    )
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        series_ids = ("DGS2", "DGS10", "DGS30")
        raw_responses: dict[str, str] = {}
        latest_by_series: dict[str, dict[str, str]] = {}
        errors: dict[str, str] = {}
        request_urls: dict[str, str] = {}

        session = requests.Session()
        session.headers.update(HEADERS)

        for series in series_ids:
            params = {
                "id": series,
                "cosd": start_date.isoformat(),
                "coed": end_date.isoformat(),
            }
            request_url = f"{FRED_SOURCE_URL}?{urlencode(params)}"
            request_urls[series] = request_url
            last_error = None

            # A timeout is treated as transient: retry once with a longer
            # read window. Separate requests also avoid a large combined CSV.
            for attempt, timeout in enumerate((45, 75), start=1):
                try:
                    response = session.get(
                        request_url,
                        timeout=(15, timeout),
                        verify=True,
                    )
                    response.raise_for_status()
                    response.encoding = "utf-8"
                    csv_text = response.text
                    reader = csv.DictReader(io.StringIO(csv_text))
                    rows = list(reader)
                    if not rows or not reader.fieldnames:
                        raise RuntimeError(f"FRED returned an empty CSV for {series}.")
                    date_field = reader.fieldnames[0]
                    observations = [
                        row for row in rows
                        if row.get(series) not in (None, "", ".")
                    ]
                    if not observations:
                        raise RuntimeError(f"FRED CSV contained no observations for {series}.")
                    latest_by_series[series] = max(
                        observations, key=lambda row: row.get(date_field, "")
                    )
                    raw_responses[series] = csv_text
                    last_error = None
                    break
                except (requests.RequestException, RuntimeError, ValueError) as exc:
                    last_error = f"attempt {attempt}: {type(exc).__name__}: {exc}"
                    if attempt == 1:
                        import time
                        time.sleep(3)

            if last_error:
                errors[series] = last_error

        result["request_url"] = request_urls
        result["raw_data"] = raw_responses
        result["parsed_data"] = {
            "series": list(series_ids),
            "units": "percent per annum",
            "latest_observations": latest_by_series,
            "series_errors": errors,
        }
        if errors:
            raise RuntimeError(
                "FRED did not return all required Treasury series: "
                + "; ".join(f"{key}={value}" for key, value in errors.items())
            )

        dates = [row.get("observation_date", row.get("DATE", "")) for row in latest_by_series.values()]
        result["data_date"] = max((value for value in dates if value), default=None)
        result["status"] = "success"
        result["success"] = True
        return result
    except Exception as exc:
        return finish_error(result, exc)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def run_treasury() -> dict[str, Any]:
    result = base_result(
        "U.S. Department of the Treasury - Daily Treasury Par Yield Curve Rates",
        TREASURY_SOURCE_URL,
    )
    try:
        year = date.today().year
        params = {
            "data": "daily_treasury_yield_curve",
            "field_tdr_date_value": str(year),
        }
        request_url = f"{TREASURY_XML_BASE}?{urlencode(params)}"
        response = requests.get(
            request_url,
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
            verify=True,
        )
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        raw_text = response.text
        root = ET.fromstring(raw_text)
        rows: list[dict[str, Any]] = []
        for entry in root.iter():
            if local_name(entry.tag) != "entry":
                continue
            row: dict[str, Any] = {}
            for child in entry.iter():
                name = local_name(child.tag)
                if name in {"NEW_DATE", "BC_2YEAR", "BC_10YEAR", "BC_30YEAR"}:
                    row[name] = child.text
            if row.get("NEW_DATE"):
                rows.append(row)

        if not rows:
            raise RuntimeError(
                "Treasury XML was received but no daily yield-curve records were parsed."
            )
        rows.sort(key=lambda row: row.get("NEW_DATE", ""))
        latest = rows[-1]
        required = ("BC_2YEAR", "BC_10YEAR", "BC_30YEAR")
        if not any(latest.get(key) not in (None, "") for key in required):
            raise RuntimeError("Latest Treasury record has no 2-, 10-, or 30-year yield values.")

        result["request_url"] = request_url
        result["data_date"] = latest.get("NEW_DATE")
        result["raw_data"] = raw_text
        result["parsed_data"] = {
            "latest_observation": latest,
            "recent_observations": rows[-10:],
            "yield_unit": "percent per annum",
            "method_note": (
                "Daily Treasury par yield curve rates (CMT); not the monthly average "
                "interest-rate dataset in FiscalData."
            ),
        }
        result["status"] = "success"
        result["success"] = True
        return result
    except Exception as exc:
        return finish_error(result, exc)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tests = [
        ("nbs", run_nbs),
        ("fred", run_fred),
        ("treasury", run_treasury),
    ]
    summary = {
        "run_at": now_iso(),
        "repository": "https://github.com/wheatshine-crypto/ChatGPT-Morning-Brief",
        "results": [],
    }
    for name, runner in tests:
        result = runner()
        save_result(name, result)
        summary["results"].append({
            "source": result["source_name"],
            "status": result["status"],
            "success": result["success"],
            "data_date": result["data_date"],
            "source_url": result["source_url"],
            "result_file": f"tests/output/{name}.json",
            "error": result["error"],
        })
        print(f"[{result['status'].upper()}] {name}: data_date={result['data_date']}")
        if result["error"]:
            print(f"  {result['error']}")

    passed = sum(1 for item in summary["results"] if item["success"])
    summary["passed"] = passed
    summary["total"] = len(tests)
    summary["overall_status"] = "success" if passed == len(tests) else "partial_or_failed"
    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nOverall: {passed}/{len(tests)} passed")
    print(f"Detailed output: {OUTPUT_DIR}")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
