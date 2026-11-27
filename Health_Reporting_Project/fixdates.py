
import pandas as pd

# Read original CSV
df = pd.read_csv("Hospital_Dataset_Final.csv")

# Convert dates into MySQL-compatible format
df["Date"] = pd.to_datetime(
    df["Date"],
    format="%d-%m-%Y",
    errors="raise"
).dt.strftime("%Y-%m-%d")

# Save a separate cleaned CSV
df.to_csv(
    "Hospital_Dataset_Cleaned.csv",
    index=False
)

print("Date conversion completed!")
print("Total records:", len(df))
print("\nFirst five dates:")
print(df["Date"].head())
