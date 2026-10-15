"""Run deterministic smoke examples against the frozen Hyderabad snapshot."""
from app.criteria_agent import run_criteria_agent
from app.retrieval_agent import RetrievalAgent


def main() -> None:
    retrieval = RetrievalAgent()
    examples = [
        (
            "exact_locality_filter",
            {
                "city": "Hyderabad",
                "locality": "Gachibowli",
                "bhk": 2,
                "property_type": "Residential Apartment",
                "min_price_inr": 5_000_000,
                "max_price_inr": 10_000_000,
                "start_month": "2022-09",
                "end_month": "2023-08",
            },
        ),
        (
            "exact_locality_id",
            {"city": "Hyderabad", "locality": "5561"},
        ),
        (
            "geo_radius_filter",
            {
                "city": "Hyderabad",
                "locality": "Kondapur",
                "geo_radius_km": 2,
                "property_type": "Residential Apartment",
                "bhk": 2,
            },
        ),
    ]

    for label, request in examples:
        criteria = run_criteria_agent(request)
        result = retrieval.retrieve(criteria)
        print(f"\n=== {label} ===")
        print(result.to_dict())
        print("PROP_IDs:", result.rows["PROP_ID"].astype(str).tolist())


if __name__ == "__main__":
    main()
