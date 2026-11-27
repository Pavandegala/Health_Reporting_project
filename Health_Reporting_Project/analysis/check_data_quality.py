
import pandas as pd
import mysql.connector
from getpass import getpass

print("Starting Data Quality Investigation...")

connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Sahana@16",
    database="health_reporting_db"
)

df = pd.read_sql(
    "SELECT * FROM health_reports",
    connection
)

connection.close()

print("\n========== DATABASE INVESTIGATION ==========")

# 1. Total records
print("\nTOTAL RECORDS:", len(df))

# 2. Column names
print("\nAVAILABLE COLUMNS:")
print(df.columns.tolist())

# 3. Missing values: NULL, empty and whitespace
print("\nMISSING VALUE ANALYSIS:")

for column in df.columns:
    null_count = df[column].isna().sum()

    blank_count = (
        df[column]
        .astype("string")
        .str.strip()
        .eq("")
        .fillna(False)
        .sum()
    )

    total_missing = null_count + blank_count

    if total_missing > 0:
        print(
            f"{column}: NULL={null_count}, "
            f"Blank={blank_count}, "
            f"Total={total_missing}"
        )

# 4. Submission values
print("\nSUBMITTED COLUMN VALUES:")

if "Submitted" in df.columns:
    print(df["Submitted"].value_counts(dropna=False))

# 5. Report status values
print("\nREPORT STATUS VALUES:")

if "Report_Status" in df.columns:
    print(df["Report_Status"].value_counts(dropna=False))

# 6. Exact duplicate rows
print("\nEXACT DUPLICATE ROWS:")
print(df.duplicated().sum())

# 7. Duplicate hospital-date combinations
print("\nDUPLICATE HOSPITAL-DATE RECORDS:")
print(
    df.duplicated(
        subset=["Hospital_ID", "Report_Date"]
    ).sum()
)

# 8. Duplicate hospital-date-disease combinations
print("\nDUPLICATE HOSPITAL-DATE-DISEASE RECORDS:")
print(
    df.duplicated(
        subset=["Hospital_ID", "Report_Date", "Disease"]
    ).sum()
)

# 9. Invalid case counts
if "Cases" in df.columns:
    cases = pd.to_numeric(df["Cases"], errors="coerce")

    print("\nINVALID CASE COUNTS:")
    print(
        (cases.notna() & (cases < 0)).sum()
    )

    print("Missing case counts:", cases.isna().sum())

# 10. Invalid delay values
if "Delay_Minutes" in df.columns:
    delays = pd.to_numeric(
        df["Delay_Minutes"],
        errors="coerce"
    )

    print("\nINVALID DELAY VALUES:")
    print(
        (delays.notna() & (delays < 0)).sum()
    )

print("\n============================================")
print("INVESTIGATION COMPLETED!")
