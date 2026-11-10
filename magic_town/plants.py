"""Plant occurrence records from Mongolia, as published by GBIF."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from magic_town.errors import FetchError
from magic_town.http_json import get_json

SOURCE_NAME = "GBIF"
SEARCH_URL = "https://api.gbif.org/v1/occurrence/search"
PAGE_SIZE = 40
LOCAL_TZ = timezone(timedelta(hours=8))

BASIS_LABELS = {
    "HUMAN_OBSERVATION": ("Human observation", "Хүний ажиглалт"),
    "OBSERVATION": ("Observation", "Ажиглалт"),
    "PRESERVED_SPECIMEN": ("Preserved specimen", "Хадгалсан дээж"),
    "LIVING_SPECIMEN": ("Living specimen", "Амьд дээж"),
    "FOSSIL_SPECIMEN": ("Fossil specimen", "Чулуужсан дээж"),
    "MATERIAL_SAMPLE": ("Material sample", "Материалын дээж"),
    "MACHINE_OBSERVATION": ("Machine observation", "Төхөөрөмжийн ажиглалт"),
    "MATERIAL_CITATION": ("Material citation", "Материалын ишлэл"),
    "OCCURRENCE": ("Occurrence", "Тохиолдол"),
}


def basis_label(code: str | None, lang: str) -> str:
    if not code:
        return "—"
    pair = BASIS_LABELS.get(code)
    if pair is None:
        return code
    return pair[0] if lang == "en" else pair[1]


def fetch_plants() -> dict:
    params = {
        "country": "MN",
        "kingdomKey": 6,
        "limit": PAGE_SIZE,
        "offset": 0,
    }
    body, final_url = get_json(SEARCH_URL, params)
    payload = _normalize(body)
    validate_plants_payload(payload)
    fetched_at = datetime.now(LOCAL_TZ).replace(microsecond=0)
    return {
        "fetched_at": fetched_at.isoformat(),
        "fetched_at_epoch": time.time(),
        "source_name": SOURCE_NAME,
        "source_url": final_url,
        "payload": payload,
    }


def validate_plants_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise FetchError("shape", "plant payload is not an object")
    total = payload.get("total_count")
    records = payload.get("records")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise FetchError("shape", "GBIF count is missing")
    if not isinstance(records, list):
        raise FetchError("shape", "GBIF results are missing")
    if payload.get("returned") != len(records):
        raise FetchError("shape", "returned count does not match records")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise FetchError("shape", f"record {index} is not an object")
        if not record.get("scientific_name") and not record.get("gbif_id"):
            raise FetchError("shape", f"record {index} has no identity")
        lat = record.get("latitude")
        lon = record.get("longitude")
        if lat is not None and (isinstance(lat, bool) or not isinstance(lat, (int, float))):
            raise FetchError("shape", f"record {index} latitude is invalid")
        if lon is not None and (isinstance(lon, bool) or not isinstance(lon, (int, float))):
            raise FetchError("shape", f"record {index} longitude is invalid")


def _normalize(body: dict) -> dict:
    total = body.get("count")
    results = body.get("results")
    if isinstance(total, bool) or not isinstance(total, int):
        raise FetchError("shape", "GBIF count is missing")
    if not isinstance(results, list):
        raise FetchError("shape", "GBIF results are missing")

    records = []
    for item in results:
        if not isinstance(item, dict):
            continue
        kingdom = item.get("kingdom")
        if isinstance(kingdom, str) and kingdom.lower() != "plantae":
            continue
        country = item.get("countryCode")
        if isinstance(country, str) and country.upper() != "MN":
            continue
        scientific = item.get("scientificName")
        gbif_id = item.get("gbifID")
        if not isinstance(scientific, str):
            scientific = None
        if gbif_id is None:
            gbif_text = None
        else:
            gbif_text = str(gbif_id)
        if not scientific and not gbif_text:
            continue
        lat = _coord(item.get("decimalLatitude"))
        lon = _coord(item.get("decimalLongitude"))
        occurrence_url = f"https://www.gbif.org/occurrence/{gbif_text}" if gbif_text else None
        records.append(
            {
                "gbif_id": gbif_text,
                "scientific_name": scientific,
                "vernacular_name": _text(item.get("vernacularName")),
                "family": _text(item.get("family")),
                "state_province": _text(item.get("stateProvince")),
                "locality": _text(item.get("locality")),
                "event_date": _text(item.get("eventDate")),
                "basis_of_record": _text(item.get("basisOfRecord")),
                "dataset_name": _text(item.get("datasetName")),
                "recorded_by": _text(item.get("recordedBy")),
                "latitude": lat,
                "longitude": lon,
                "occurrence_url": occurrence_url,
            }
        )

    if results and not records:
        raise FetchError("shape", "GBIF returned rows, but none were usable plant records")

    return {
        "country": "MN",
        "kingdom": "Plantae",
        "total_count": total,
        "returned": len(records),
        "limit": PAGE_SIZE,
        "records": records,
    }


def _text(value) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coord(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
