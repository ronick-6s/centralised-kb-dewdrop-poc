from dataclasses import dataclass
from typing import Any, Dict

@dataclass
class Document:
    content: str
    metadata: Dict[str, Any]
