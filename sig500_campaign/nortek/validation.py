from __future__ import annotations

from .deploy_parser import DeployDocument


EXPECTED_REFERENCE = {
    "SETPLAN": {"MIAVG": 600, "AVG": 1, "BURST": 1, "MIBURST": 600},
    "SETAVG": {"AI": 600, "NPING": 122, "NB": 4, "NC": 43, "CS": 0.5, "BD": 0.5, "CY": "ENU"},
    "SETBURST": {"SR": 2, "NS": 1200, "NB": 1, "CH": 5, "ECHO": 1},
    "SETECHO": {"NC": 3633, "BINSIZE": 0.006, "BD": 0.5, "FREQ1": 500, "XMIT1": 1, "PL1": 0, "PULSECOMP1": 1},
}


def compare_reference(document: DeployDocument) -> list[dict[str, object]]:
    result = []
    for command, parameters in EXPECTED_REFERENCE.items():
        for parameter, expected in parameters.items():
            try:
                actual = document.get(command, parameter)
            except KeyError:
                actual = None
            result.append(
                {"field": f"{command}.{parameter}", "expected": expected, "actual": actual, "matches": actual == expected}
            )
    return result


def echo_end_range_m(document: DeployDocument) -> float:
    return round(
        float(document.get("SETECHO", "BD"))
        + float(document.get("SETECHO", "NC")) * float(document.get("SETECHO", "BINSIZE")),
        12,
    )
