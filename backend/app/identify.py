"""Plant identification behind a small provider interface.

Routers depend on ``get_identify_provider`` only. Issue 012 swaps the stub for a
real provider by changing that one function.
"""

import struct
from typing import Annotated, Protocol

from fastapi import Depends

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


def get_identify_provider(store: Annotated[StoreProtocol, Depends(get_store)]) -> IdentifyProvider:
    """Dependency: the provider used by ``POST /plants/identify``."""
    return StubIdentifyProvider(store.list_plants())
