"""Directory → tree structure for the web UI."""

from pathlib import Path


def _build_case_tree(cases: list[dict], scan_dir: str) -> dict:
    """Build a recursive dir→file→case tree from a flat case list."""
    base = Path(scan_dir).resolve()
    root: dict = {
        "name": base.name,
        "type": "dir",
        "relpath": "",
        "children": [],
        "total_cases": 0,
    }

    for c in cases:
        filepath = c.get("file", "")
        try:
            source = Path(filepath)
            # YAML metadata is relative to the project, not the runner process cwd.
            if not source.is_absolute():
                source = base / source
            rel = source.resolve().relative_to(base)
        except (ValueError, OSError):
            rel = Path(Path(filepath).name)

        parts = rel.parts
        if not parts:
            continue

        current = root
        for i, part in enumerate(parts[:-1]):
            found = None
            for child in current.get("children", []):
                if child["type"] == "dir" and child["name"] == part:
                    found = child
                    break
            if found is None:
                found = {
                    "name": part,
                    "type": "dir",
                    "relpath": str(Path(*parts[: i + 1])),
                    "children": [],
                    "total_cases": 0,
                }
                current.setdefault("children", []).append(found)
            current = found

        filename = parts[-1]
        file_node = None
        for child in current.get("children", []):
            if child["type"] == "file" and child["name"] == filename:
                file_node = child
                break
        if file_node is None:
            file_node = {
                "name": filename,
                "type": "file",
                "relpath": str(rel),
                "cases": [],
            }
            current.setdefault("children", []).append(file_node)
        file_node.setdefault("cases", []).append(c)

    def _compute_counts(node: dict) -> int:
        if node["type"] == "file":
            node["case_count"] = len(node["cases"])
            node["cases"].sort(key=lambda x: x.get("name", ""))
            return node["case_count"]
        total = 0
        for child in node.get("children", []):
            total += _compute_counts(child)
        node["total_cases"] = total
        return total

    def _sort_tree(node: dict) -> None:
        if "children" in node:
            node["children"].sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
            for child in node["children"]:
                _sort_tree(child)

    _compute_counts(root)
    _sort_tree(root)
    return root
