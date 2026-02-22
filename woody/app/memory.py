"""Long-term memory via vector store (Chromadb). Uses shared memory store."""

from typing import List, Optional, Union

from shared.memory import memory_add as _add, memory_search as _search


def memory_add(
    text: str,
    metadata: Optional[dict] = None,
    weight: int = 5,
    memory_type: str = "long",
) -> Optional[str]:
    return _add(text, metadata, weight=weight, memory_type=memory_type)


def memory_search(
    query: str,
    n: int = 5,
    memory_type: Optional[str] = None,
    use_weight: bool = True,
    with_ids: bool = False,
) -> Union[List[str], List[dict]]:
    return _search(query, n=n, memory_type=memory_type, use_weight=use_weight, with_ids=with_ids)
