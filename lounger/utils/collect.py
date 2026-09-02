import json
import re

import pytest

#: Fields parsed from a test docstring / markers for platform ingestion (F1).
#: Docstring convention (one per line):
#:   author: <name>
#:   priority: P0 | P1 | P2 | P3
#:   tags: tag1, tag2
_DOC_AUTHOR_RE = re.compile(r"^\s*author\s*:\s*(\S.*?)\s*$", re.MULTILINE)
_DOC_PRIORITY_RE = re.compile(r"^\s*priority\s*:\s*(P[0-3])\s*$", re.IGNORECASE | re.MULTILINE)
_DOC_TAGS_RE = re.compile(r"^\s*tags?\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def _split_tags(tags_text: str) -> list[str]:
    """Split a tags line into a clean list (comma / space separated)."""
    parts = re.split(r"[,，;；\s]+", tags_text.strip())
    return [p for p in parts if p]


def _parse_doc_metadata(doc: str | None) -> dict:
    """Extract author/priority/tags from a docstring."""
    doc = doc or ""
    metadata: dict = {}

    m = _DOC_AUTHOR_RE.search(doc)
    if m:
        metadata["author"] = m.group(1).strip()

    m = _DOC_PRIORITY_RE.search(doc)
    if m:
        metadata["priority"] = m.group(1).upper()

    m = _DOC_TAGS_RE.search(doc)
    if m:
        metadata["tags"] = _split_tags(m.group(1))

    return metadata


class JsonCollector:
    def __init__(self):
        self.test_data = []

    def pytest_collection_modifyitems(self, items):
        """
        Collect test cases and handle parameterized tests by extracting case names
        from parameters and appending them to docstrings.
        """
        # Collect all test case information
        for item in items:
            # Extract basic test case information
            doc = item.obj.__doc__
            markers = [m.name for m in item.own_markers]  # Decorators/tags
            doc_meta = _parse_doc_metadata(doc)

            # markers: custom pytest marks other than parametrize/skip are
            # surfaced as tags too (platform ingestion)
            extra_tags = [mk for mk in markers if mk not in ("parametrize", "skip", "env", "integration")]
            tags = list(dict.fromkeys(doc_meta.get("tags", []) + extra_tags))

            case_info = {
                "file": str(item.fspath),  # File path
                "nodeid": item.nodeid,  # Unique identifier
                "name": item.name,  # Method name
                "parent": item.parent.name,  # Class name or module name
                "description": doc,  # Docstring (comments)
                "markers": markers,  # Decorators/tags
                # Platform metadata (F1): from docstring / markers
                "author": doc_meta.get("author", ""),
                "priority": doc_meta.get("priority", ""),
                "tags": tags,
            }
            self.test_data.append(case_info)


def get_test_cases(path):
    collector = JsonCollector()
    # Use --collect-only parameter to prevent test execution
    pytest.main([
        "--collect-only",
        "-W", "ignore::pytest.PytestAssertRewriteWarning",
        path
    ], plugins=[collector])
    return collector.test_data


if __name__ == "__main__":
    cases = get_test_cases("./")
    print(json.dumps(cases, indent=4, ensure_ascii=False))
