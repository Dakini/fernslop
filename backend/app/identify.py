"""Plant identification behind a small provider interface.

Routers depend on ``get_identify_provider`` only. With
``FERNSLOP_IDENTIFY_PROVIDER=plantnet`` and a non-blank ``FERNSLOP_IDENTIFY_API_KEY``
it returns the Pl@ntNet provider; anything else returns the stub.
"""

import logging
import os
import re
import struct
from typing import Annotated, Protocol

import httpx
from fastapi import Depends

from pydantic import ValidationError

from app.models import IdentifyCandidate, Plant
from app.store import StoreProtocol, get_store
from app.uploads import ValidatedImage

IDENTIFY_FAILED_MESSAGE = "We couldn't identify that photo — try again"


class IdentifyError(Exception):
    """Raised by a provider when identification fails; the route turns it into a 502."""


class IdentifyProvider(Protocol):
    def identify(self, image: ValidatedImage) -> list[IdentifyCandidate]: ...


_STUB_CONFIDENCES = (0.82, 0.11, 0.04)
_STUB_STEP = 7
_UINT32 = 2**32


def _stub_hash(filename: str, size: int) -> int:
    """The mock's string hash: 31-based over UTF-16 code units, mod 2**32."""
    encoded = (filename + str(size)).encode("utf-16-le", errors="surrogatepass")
    h = 0
    for (unit,) in struct.iter_unpack("<H", encoded):
        h = (h * 31 + unit) % _UINT32
    return h


class StubIdentifyProvider:
    """Deterministic fake: picks reference plants from a hash of the filename and size."""

    def __init__(self, plants: list[Plant]) -> None:
        self._plants = plants

    def identify(self, image: ValidatedImage) -> list[IdentifyCandidate]:
        if not self._plants:
            return []
        filename = image.filename or ""
        h = _stub_hash(filename, len(image.data))
        divisor = 4 if "blurry" in filename.lower() else 1
        return [
            IdentifyCandidate(
                plant=self._plants[(h + i * _STUB_STEP) % len(self._plants)],
                confidence=confidence / divisor,
            )
            for i, confidence in enumerate(_STUB_CONFIDENCES)
        ]


PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"
PLANTNET_TIMEOUT_SECONDS = 10
_PLANTNET_CONTENT_TYPES = ("image/jpeg", "image/png")

_API_KEY_PARAM = re.compile(r"(api-key=)[^&\s\"']+")


class _RedactApiKey(logging.Filter):
    """httpx logs every request URL, which carries the key as a query parameter."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _API_KEY_PARAM.sub(r"\1***", record.getMessage())
        record.args = None
        return True


for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).addFilter(_RedactApiKey())


class PlantNetIdentifyProvider:
    """Identifies photos with the Pl@ntNet API and maps results onto reference plants."""

    def __init__(self, plants: list[Plant], api_key: str, client: httpx.Client | None = None) -> None:
        self._by_name: dict[str, Plant] = {}
        for plant in plants:
            self._by_name.setdefault(_normalise(plant.scientific_name), plant)
        self._api_key = api_key
        self._client = client

    def identify(self, image: ValidatedImage) -> list[IdentifyCandidate]:
        if image.content_type not in _PLANTNET_CONTENT_TYPES:
            raise IdentifyError("Pl@ntNet accepts only JPG and PNG images")
        # ``from None`` everywhere below: httpx errors carry the URL, which includes the key.
        try:
            response = self._post(image)
        except (httpx.HTTPError, httpx.InvalidURL):
            raise IdentifyError("Pl@ntNet request failed") from None
        if not response.is_success:
            raise IdentifyError(f"Pl@ntNet returned status {response.status_code}")
        try:
            results = response.json()["results"]
        except (ValueError, KeyError, TypeError):
            raise IdentifyError("Pl@ntNet returned an unexpected body") from None
        if not isinstance(results, list):
            raise IdentifyError("Pl@ntNet returned an unexpected body")
        return self._map(results)

    def _post(self, image: ValidatedImage) -> httpx.Response:
        files = {"images": (image.filename or "image", image.data, image.content_type)}
        kwargs = {
            "params": {"api-key": self._api_key},
            "files": files,
            "data": {"organs": "auto"},
            "timeout": PLANTNET_TIMEOUT_SECONDS,
        }
        if self._client is not None:
            return self._client.post(PLANTNET_URL, **kwargs)
        with httpx.Client() as client:
            return client.post(PLANTNET_URL, **kwargs)

    def _map(self, results: list) -> list[IdentifyCandidate]:
        best: dict[str, IdentifyCandidate] = {}
        for item in results:
            try:
                plant = self._by_name.get(_normalise(item["species"]["scientificNameWithoutAuthor"]))
                if plant is None:
                    continue
                candidate = IdentifyCandidate(plant=plant, confidence=item["score"])
            except (KeyError, TypeError, AttributeError, ValidationError):
                continue  # a malformed item is treated like an unmatched one
            if plant.id not in best or candidate.confidence > best[plant.id].confidence:
                best[plant.id] = candidate
        return sorted(best.values(), key=lambda c: c.confidence, reverse=True)


def _normalise(name: str) -> str:
    return name.strip().casefold()


def get_identify_provider(store: Annotated[StoreProtocol, Depends(get_store)]) -> IdentifyProvider:
    """Dependency: the provider used by ``POST /plants/identify``."""
    api_key = os.environ.get("FERNSLOP_IDENTIFY_API_KEY", "").strip()
    if os.environ.get("FERNSLOP_IDENTIFY_PROVIDER") == "plantnet" and api_key:
        return PlantNetIdentifyProvider(store.list_plants(), api_key)
    return StubIdentifyProvider(store.list_plants())
