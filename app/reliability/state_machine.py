from __future__ import annotations

from app.reliability.contracts import RouteState


_ALLOWED: dict[RouteState, set[RouteState]] = {
    RouteState.UNKNOWN: {
        RouteState.PROBING,
        RouteState.QUARANTINED,
        RouteState.RETIRED,
    },
    RouteState.PROBING: {
        RouteState.HEALTHY,
        RouteState.DEGRADED,
        RouteState.QUARANTINED,
        RouteState.BLOCKED,
        RouteState.RETIRED,
    },
    RouteState.HEALTHY: {
        RouteState.PROBING,
        RouteState.DEGRADED,
        RouteState.QUARANTINED,
        RouteState.BLOCKED,
        RouteState.SHADOW,
        RouteState.RETIRED,
    },
    RouteState.DEGRADED: {
        RouteState.PROBING,
        RouteState.HEALTHY,
        RouteState.QUARANTINED,
        RouteState.BLOCKED,
        RouteState.RECERTIFYING,
        RouteState.RETIRED,
    },
    RouteState.QUARANTINED: {
        RouteState.PROBING,
        RouteState.RECERTIFYING,
        RouteState.BLOCKED,
        RouteState.RETIRED,
    },
    RouteState.RECERTIFYING: {
        RouteState.SHADOW,
        RouteState.QUARANTINED,
        RouteState.BLOCKED,
        RouteState.RETIRED,
    },
    RouteState.SHADOW: {
        RouteState.HEALTHY,
        RouteState.QUARANTINED,
        RouteState.BLOCKED,
        RouteState.RETIRED,
    },
    RouteState.BLOCKED: {
        RouteState.PROBING,
        RouteState.RECERTIFYING,
        RouteState.QUARANTINED,
        RouteState.RETIRED,
    },
    RouteState.RETIRED: set(),
}


class InvalidStateTransition(ValueError):
    pass


def validate_transition(current: RouteState, target: RouteState) -> None:
    if current == target:
        return
    if target not in _ALLOWED[current]:
        raise InvalidStateTransition(
            f"invalid route transition: {current.value} -> {target.value}"
        )


def next_state_for_observation(
    current: RouteState,
    *,
    hard_failure: bool,
    blocked: bool,
    signal_count: int,
    consecutive_failures: int,
) -> RouteState:
    if current == RouteState.RETIRED:
        return current
    if blocked:
        return RouteState.BLOCKED
    if hard_failure or consecutive_failures >= 2:
        return RouteState.QUARANTINED
    if signal_count:
        return RouteState.DEGRADED
    return RouteState.HEALTHY
