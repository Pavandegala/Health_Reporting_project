
import pandas as pd
import mysql.connector
from getpass import getpass

print("Starting Advanced Health Data Quality Analysis...")

# =====================================================
# 1. CONNECT TO MYSQL
# =====================================================

connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Sahana@16",
    database="health_reporting_db"
)

print("Database connected successfully!")

try:
    # Load health reports
    df = pd.read_sql(
        "SELECT * FROM health_reports",
        connection
    )

    # Load hospital master data
    hospitals = pd.read_sql(
        "SELECT * FROM hospitals",
        connection
    )

finally:
    connection.close()

print("Health reports and hospital data loaded successfully!")


# =====================================================
# 2. BASIC DATA PREPARATION
# =====================================================

total_records = len(df)

def is_missing(series):
    """Detect NULL, empty and whitespace-only values."""
    return (
        series.isna()
        | series.astype("string").str.strip().eq("").fillna(False)
    )


# Normalize important text columns
for column in [
    "Hospital_ID",
    "Hospital_Name",
    "District",
    "Disease",
    "Submitted",
    "Report_Status"
]:
    df[column] = df[column].astype("string").str.strip()


df["Submitted_Normalized"] = (
    df["Submitted"].str.lower()
)

df["Status_Normalized"] = (
    df["Report_Status"].str.lower()
)

# Convert dates and numeric columns
df["Parsed_Date"] = pd.to_datetime(
    df["Report_Date"],
    errors="coerce"
)

df["Cases_Numeric"] = pd.to_numeric(
    df["Cases"],
    errors="coerce"
)

df["Delay_Numeric"] = pd.to_numeric(
    df["Delay_Minutes"],
    errors="coerce"
)

submitted_mask = df["Submitted_Normalized"] == "yes"
not_submitted_mask = df["Submitted_Normalized"] == "no"


# =====================================================
# 3. COMPLETENESS ANALYSIS
# =====================================================

required_columns = [
    "Report_Date",
    "Hospital_ID",
    "Hospital_Name",
    "District",
    "Disease",
    "Submitted"
]

missing_by_column = {}

for column in required_columns:
    missing_by_column[column] = int(
        is_missing(df[column]).sum()
    )

total_missing_required = sum(
    missing_by_column.values()
)

total_required_values = (
    total_records * len(required_columns)
)

completeness_score = (
    (total_required_values - total_missing_required)
    / total_required_values * 100
    if total_required_values else 0
)

# Submitted reports must contain these fields
conditional_columns = [
    "Cases",
    "Submission_Time",
    "Delay_Minutes"
]

conditional_missing = {}

for column in conditional_columns:
    conditional_missing[column] = int(
        is_missing(df.loc[submitted_mask, column]).sum()
    )

unexpected_missing = sum(conditional_missing.values())

# Missing values in these fields for not-submitted reports
# are expected and are not treated as errors.
expected_missing = sum(
    int(is_missing(df.loc[not_submitted_mask, column]).sum())
    for column in conditional_columns
)


# =====================================================
# 4. VALIDITY ANALYSIS
# =====================================================

valid_dates = int(df["Parsed_Date"].notna().sum())

invalid_dates = int(
    df["Parsed_Date"].isna().sum()
)

valid_submitted_cases = (
    submitted_mask
    & df["Cases_Numeric"].notna()
    & (df["Cases_Numeric"] >= 0)
)

invalid_cases = (
    submitted_mask
    & df["Cases_Numeric"].notna()
    & (df["Cases_Numeric"] < 0)
)

missing_submitted_cases = (
    submitted_mask
    & df["Cases_Numeric"].isna()
)

valid_submitted_delays = (
    submitted_mask
    & df["Delay_Numeric"].notna()
    & (df["Delay_Numeric"] >= 0)
)

invalid_delays = (
    submitted_mask
    & df["Delay_Numeric"].notna()
    & (df["Delay_Numeric"] < 0)
)

missing_submitted_delays = (
    submitted_mask
    & df["Delay_Numeric"].isna()
)

valid_cases = int(valid_submitted_cases.sum())
invalid_cases_count = int(invalid_cases.sum())

valid_delays = int(valid_submitted_delays.sum())
invalid_delays_count = int(invalid_delays.sum())

missing_cases_count = int(missing_submitted_cases.sum())
missing_delays_count = int(missing_submitted_delays.sum())

# Invalid submission values
invalid_submission_values = int(
    (~df["Submitted_Normalized"].isin(["yes", "no"])).sum()
)

# Submission status consistency
status_mismatch = (
    (submitted_mask & ~df["Status_Normalized"].isin(["on time", "late"]))
    |
    (not_submitted_mask & (df["Status_Normalized"] != "not submitted"))
)

status_mismatches = int(status_mismatch.sum())


# =====================================================
# 5. DUPLICATE ANALYSIS
# =====================================================

# Exact duplicate records
exact_duplicates = int(df.duplicated().sum())

# Duplicate Report IDs
duplicate_report_ids = int(
    df["Report_ID"].duplicated().sum()
)

# Duplicate hospital-date-disease combinations
# Ignore rows where any key field is missing.
duplicate_keys = df[
    ["Hospital_ID", "Parsed_Date", "Disease"]
].notna().all(axis=1)

duplicate_submission_rows = int(
    df.loc[duplicate_keys].duplicated(
        subset=["Hospital_ID", "Parsed_Date", "Disease"]
    ).sum()
)


# =====================================================
# 6. HOSPITAL CONSISTENCY ANALYSIS
# =====================================================

hospital_reference = hospitals[
    ["Hospital_ID", "Hospital_Name", "District"]
].copy()

# Normalize reference values
for column in ["Hospital_ID", "Hospital_Name", "District"]:
    hospital_reference[column] = (
        hospital_reference[column].astype("string").str.strip()
    )

comparison = df.merge(
    hospital_reference,
    on="Hospital_ID",
    how="left",
    suffixes=("_report", "_master"),
    indicator=True
)

invalid_hospital_ids = int(
    (comparison["_merge"] == "left_only").sum()
)

# Compare names and districts only where Hospital_ID exists
matched = comparison[comparison["_merge"] == "both"]

name_mismatches = int(
    (
        matched["Hospital_Name_report"].str.lower()
        != matched["Hospital_Name_master"].str.lower()
    ).sum()
)

district_mismatches = int(
    (
        matched["District_report"].str.lower()
        != matched["District_master"].str.lower()
    ).sum()
)


# =====================================================
# 7. SUBMISSION PERFORMANCE
# =====================================================

submitted_count = int(submitted_mask.sum())
not_submitted_count = int(not_submitted_mask.sum())

on_time_count = int(
    (df["Status_Normalized"] == "on time").sum()
)

late_count = int(
    (df["Status_Normalized"] == "late").sum()
)

submission_rate = (
    submitted_count / total_records * 100
    if total_records else 0
)

average_delay = df.loc[
    submitted_mask, "Delay_Numeric"
].mean()


# =====================================================
# 8. DISPLAY COMPLETE REPORT
# =====================================================

print("\n")
print("=" * 55)
print("       ADVANCED HEALTH DATA QUALITY REPORT")
print("=" * 55)

print("\nTOTAL RECORDS:", total_records)


# Completeness
print("\n1. COMPLETENESS ANALYSIS")

for column, count in missing_by_column.items():
    print(f"{column}: {count} missing")

print("Total missing required values:", total_missing_required)

print(f"Completeness Score: {completeness_score:.2f}%")


# Expected and unexpected missing values
print("\n2. EXPECTED VS UNEXPECTED MISSING VALUES")

print("Expected missing values:", expected_missing)
print("Unexpected missing values:", unexpected_missing)

for column, count in conditional_missing.items():
    print(f"Missing {column} in submitted reports: {count}")


# Validity
print("\n3. VALIDITY ANALYSIS")

print("Valid report dates:", valid_dates)
print("Invalid report dates:", invalid_dates)

print("Valid case counts:", valid_cases)
print("Negative case counts:", invalid_cases_count)
print("Missing case counts in submitted reports:", missing_cases_count)

print("Valid delay values:", valid_delays)
print("Negative delay values:", invalid_delays_count)
print("Missing delay values in submitted reports:", missing_delays_count)

print("Invalid submission values:", invalid_submission_values)
print("Submission status mismatches:", status_mismatches)


# Uniqueness
print("\n4. UNIQUENESS ANALYSIS")

print("Exact duplicate rows:", exact_duplicates)
print("Duplicate Report IDs:", duplicate_report_ids)
print("Duplicate hospital-date-disease records:", duplicate_submission_rows)


# Consistency
print("\n5. CONSISTENCY ANALYSIS")

print("Invalid Hospital IDs:", invalid_hospital_ids)
print("Hospital Name mismatches:", name_mismatches)
print("District mismatches:", district_mismatches)


# Timeliness
print("\n6. SUBMISSION PERFORMANCE")

print("Total submitted:", submitted_count)
print("Total not submitted:", not_submitted_count)
print("On-time reports:", on_time_count)
print("Late reports:", late_count)

print(f"Submission Rate: {submission_rate:.2f}%")

if pd.notna(average_delay):
    print(f"Average Delay: {average_delay:.2f} minutes")
else:
    print("Average Delay: Not available")


print("\n" + "=" * 55)
print("       DATA QUALITY ANALYSIS COMPLETED!")
print("=" * 55)
