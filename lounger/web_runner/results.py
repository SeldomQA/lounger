"""JUnit ingestion without guessing pytest node IDs from display names."""

from xml.etree import ElementTree


def parse_junit(path):
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("JUnit report exceeds 32 MiB; raw report and logs remain available")
    root = ElementTree.parse(path).getroot()
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("Unsupported JUnit root element")
    results = []
    counts = dict(passed=0, failed=0, error=0, skipped=0, total=0)
    for case in root.iter("testcase"):
        outcome, message = "passed", ""
        for name, mapped in [("error", "error"), ("failure", "failed"), ("skipped", "skipped")]:
            element = case.find(name)
            if element is not None:
                outcome = mapped
                message = element.get("message", "") + "\n" + (element.text or "")
                break
        counts[outcome] += 1
        counts["total"] += 1
        results.append(
            dict(
                nodeid=None,
                name=case.get("name", ""),
                classname=case.get("classname", ""),
                outcome=outcome,
                duration_ms=round(float(case.get("time", "0")) * 1000),
                failure_text=message.strip(),
                stdout=case.findtext("system-out", ""),
                stderr=case.findtext("system-err", ""),
            )
        )
    return results, counts
