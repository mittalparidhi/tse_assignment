import pandas as pd

path = "data/raw/hyderabad.csv"
df = pd.read_csv(path, nrows=10, low_memory=False)

print("=== REQUIRED FIELD CHECK ===")
for name in ["REGISTER_DATE__", "MAP_DETAILS", "location", "POSTING_DATE", "PROP_ID"]:
    print(f"{name}: {'PRESENT' if name in df.columns else 'MISSING'}")

print("\n=== FIELD SAMPLES ===")
for name in ["REGISTER_DATE__", "MAP_DETAILS", "location"]:
    if name in df.columns:
        print(f"\n{name}:")
        values = df[name].dropna().astype(str).head(3)
        for value in values:
            print(value[:400])
