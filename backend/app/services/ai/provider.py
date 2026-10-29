from typing import Protocol


class AIProvider(Protocol):
    def generate_structured_profile(self, metadata_json: str) -> str: ...
