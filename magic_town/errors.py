"""Errors for live API calls. These never carry invented observations."""


class FetchError(Exception):
    """A real request failed or the real response could not be used."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")
