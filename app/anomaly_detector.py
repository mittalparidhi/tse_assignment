
"""Deterministic anomaly rules for the Hyderabad monthly snapshot."""

from typing import Any


PRICE_CHANGE_THRESHOLD = 0.12
COUNT_DROP_RATIO = 0.50
COUNT_SPIKE_RATIO = 2.0
FINAL_MONTH_CONCENTRATION_THRESHOLD = 0.70


def detect_anomalies(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic anomaly flags from ordered monthly records."""
    if not records:
        raise ValueError("At least one monthly record is required.")

    months = [record["month"] for record in records]
    if months != sorted(months) or len(months) != len(set(months)):
        raise ValueError("Monthly records must be chronologically ordered and unique.")

    flags: list[dict[str, Any]] = []

    def add_flag(
        rule_id: str,
        month: str,
        metric: str,
        message: str,
        **details: Any,
    ) -> None:
        flags.append(
            {
                "rule_id": rule_id,
                "month": month,
                "metric": metric,
                "message": message,
                **details,
            }
        )

    # AN-01: large changes in either verified INR price-bound median.
    price_fields = (
        ("median_min_price_inr", "median_min_price_inr"),
        ("median_max_price_inr", "median_max_price_inr"),
    )

    for previous, current in zip(records, records[1:]):
        for field, metric in price_fields:
            old = previous[field]
            new = current[field]

            # Do not calculate a percentage change from missing or invalid data.
            if old is None or new is None or old <= 0 or new <= 0:
                continue

            change = (new - old) / old

            if abs(change) > PRICE_CHANGE_THRESHOLD:
                direction = "increase" if change > 0 else "decrease"
                add_flag(
                    "AN-01",
                    current["month"],
                    metric,
                    f"{direction.capitalize()} of {abs(change):.2%} "
                    f"from {previous['month']} to {current['month']}.",
                    previous_month=previous["month"],
                    previous_value=old,
                    current_value=new,
                    change_fraction=change,
                    threshold=PRICE_CHANGE_THRESHOLD,
                )

    # AN-02 and AN-03: changes in observed posting counts.
    for previous, current in zip(records, records[1:]):
        old = previous["observed_listing_count"]
        new = current["observed_listing_count"]

        if old <= 0:
            continue

        ratio = new / old

        if ratio <= COUNT_DROP_RATIO:
            add_flag(
                "AN-02",
                current["month"],
                "observed_listing_count",
                f"Observed count fell to {ratio:.2f}x the previous month.",
                previous_month=previous["month"],
                previous_value=old,
                current_value=new,
                ratio=ratio,
                threshold=COUNT_DROP_RATIO,
            )

        if ratio >= COUNT_SPIKE_RATIO:
            add_flag(
                "AN-03",
                current["month"],
                "observed_listing_count",
                f"Observed count reached {ratio:.2f}x the previous month.",
                previous_month=previous["month"],
                previous_value=old,
                current_value=new,
                ratio=ratio,
                threshold=COUNT_SPIKE_RATIO,
            )

    # AN-04: concentration in the final two observed months.
    total = sum(record["observed_listing_count"] for record in records)

    if len(records) >= 2 and total > 0:
        final_two = records[-2:]
        final_count = sum(
            record["observed_listing_count"] for record in final_two
        )
        fraction = final_count / total

        if fraction >= FINAL_MONTH_CONCENTRATION_THRESHOLD:
            add_flag(
                "AN-04",
                final_two[-1]["month"],
                "final_two_month_concentration",
                "The final two months account for "
                f"{fraction:.2%} of all observed rows.",
                window_start=final_two[0]["month"],
                window_end=final_two[-1]["month"],
                numerator=final_count,
                denominator=total,
                fraction=fraction,
                threshold=FINAL_MONTH_CONCENTRATION_THRESHOLD,
            )

    # Explicit sorting makes output independent of rule implementation order.
    rule_order = {"AN-01": 1, "AN-02": 2, "AN-03": 3, "AN-04": 4}
    return sorted(
        flags,
        key=lambda flag: (
            flag["month"],
            rule_order[flag["rule_id"]],
            flag["metric"],
        ),
    )
