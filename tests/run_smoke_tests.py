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
            timeout=TIMEOUT_SECONDS,
            max_retries=1,
            retry_backoff=0,
            auto_session=result["auto_browser_session"],
        )
        result["request_url"] = (
            "https://data.stats.gov.cn/dg/website/publicrelease/web/external/"
            "new/queryIndexTreeAsync (and related public monthly-data endpoints)"
        )

        roots = client.tree("monthData")
        result["raw_data"] = {"root_catalogue": roots}
        if not isinstance(roots, list) or not roots:
            raise RuntimeError("NBS returned an empty monthly-data catalogue.")

        # Bounded breadth-first traversal: locate a CPI-related catalogue node.
        queue: list[tuple[dict[str, Any], list[str]]] = [
            (node, [str(node.get("name", ""))]) for node in roots if isinstance(node, dict)
        ]
        visited = 0
        max_nodes = 45
        max_depth = 6
        keywords = ("居民消费价格指数", "居民消费价格", "CPI")
        candidate = None

        while queue and visited < max_nodes:
            node, path = queue.pop(0)
            visited += 1
            node_id = node.get("_id")
            node_name = str(node.get("name", ""))
            if node_id and any(word in node_name.upper() for word in keywords):
                items = client.indicators("monthData", cid=str(node_id))
                if items:
                    candidate = (node, path, items)
                    break
            if len(path) < max_depth and node_id:
                children = client.tree("monthData", pid=str(node_id))
                for child in children:
                    if isinstance(child, dict):
                        queue.append((child, path + [str(child.get("name", ""))]))

        result["catalogue_nodes_checked"] = visited
        if candidate is None:
            raise RuntimeError(
                "Could not locate a CPI-related monthly indicator within the bounded "
                f"catalogue scan ({visited} nodes). The root catalogue is preserved in raw_data."
            )

        node, path, indicators = candidate
        preferred = next(
            (
                item for item in indicators
                if item.get("series_type") == "yoy_growth"
                or "同比" in str(item.get("label", ""))
            ),
            indicators[0],
        )
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
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=21)
        params = {
            "id": "DGS2,DGS10,DGS30",
            "cosd": start_date.isoformat(),
            "coed": end_date.isoformat(),
        }
        request_url = f"{FRED_SOURCE_URL}?{urlencode(params)}"
        response = requests.get(
            request_url,
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
            verify=True,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        text = response.text
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows or not reader.fieldnames:
            raise RuntimeError("FRED returned an empty CSV response.")
        date_field = reader.fieldnames[0]
        observations = [
            row for row in rows
            if any(row.get(series) not in (None, "", ".") for series in ("DGS2", "DGS10", "DGS30"))
        ]
        if not observations:
            raise RuntimeError("FRED CSV contained no non-missing yield observations.")
        latest = max(observations, key=lambda row: row.get(date_field, ""))
        result["request_url"] = request_url
        result["data_date"] = latest.get(date_field)
        result["raw_data"] = text
        result["parsed_data"] = {
            "series": ["DGS2", "DGS10", "DGS30"],
            "units": "percent per annum",
            "latest_observation": latest,
            "recent_observations": observations[-10:],
        }
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
