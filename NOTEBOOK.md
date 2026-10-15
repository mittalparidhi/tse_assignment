# Project Notebook


## Dataset Decision: Real Snapshot for the Headline Run

### Primary dataset
The headline run uses the supplied real Hyderabad property-listing snapshot. The raw source remains under `data/raw/`, and the deterministic cleaned dataset is `data/processed/hyderabad_clean.csv`.

### Missing-month policy
Do not synthesize, interpolate, or extrapolate missing monthly records. Report the source-period months using their observed data and actual coverage status. Distinguish months with no listings from months with unavailable or incomplete data. August 2023 is a partial month because the latest observed posting date is August 26, 2023.

### Synthetic data policy
If synthetic data is later used for a separate diagnostic experiment, explicitly label it as synthetic and report its results separately from the real-snapshot headline results. Never combine synthetic observations with the real dataset to fill missing months or present synthetic results as observed market evidence.

### Reporting limitations
Monthly listing counts describe listings observed in the supplied snapshot, not a census of the Hyderabad property market. Keep unverified metrics explicitly unverified and unsupported values null rather than fabricating values.

