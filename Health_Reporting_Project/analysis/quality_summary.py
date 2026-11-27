
import pandas as pd
import mysql.connector
from getpass import getpass

print("Starting Data Quality Summary...")

# 1. Connect to MySQL
connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Sahana@16",
    database="health_reporting_db"
)

print("Database connected successfully!")

# 2. Load both database tables
cursor = connection.cursor(dictionary=True)

cursor.execute("SELECT * FROM health_reports")
reports = pd.DataFrame(cursor.fetchall())

cursor.execute("SELECT * FROM hospitals")
hospitals = pd.DataFrame(cursor.fetchall())

cursor.close()
connection.close()

print("Health reports and hospital data loaded!")


# ==========================================
# 3. COMPLETENESS
# ==========================================

required_columns = [
    "Report_Date",
    "Hospital_ID",
    "Hospital_Name",
    "District",
    "Disease",
    "Submitted"
]

total_records = len(reports)

missing_values = reports[required_columns].isna().sum().sum()

total_required_values = total_records * len(required_columns)

completeness_score = (
    (total_required_values - missing_values)
    / total_required_values * 100
    if total_required_values > 0 else 0
)


# ==========================================
# 4. VALIDITY
# ==========================================

reports["Report_Date"] = pd.to_datetime(
    reports["Report_Date"],
    errors="coerce"
)

valid_dates = reports["Report_Date"].notna().sum()

submitted = reports[
    reports["Submitted"].astype(str).str.strip().str.casefold() == "yes"
]

valid_cases = (
    submitted["Cases"].notna()
    & (submitted["Cases"] >= 0)
).sum()

valid_delays = (
    submitted["Delay_Minutes"].notna()
    & (submitted["Delay_Minutes"] >= 0)
).sum()

submitted_count = len(submitted)

validity_score = (
    (valid_dates + valid_cases + valid_delays)
    / (total_records + 2 * submitted_count) * 100
    if total_records + 2 * submitted_count > 0 else 0
)


# ==========================================
# 5. UNIQUENESS
# ==========================================

duplicate_rows = reports.duplicated().sum()

duplicate_reports = reports.duplicated(
    subset=["Hospital_ID", "Report_Date"]
).sum()


# ==========================================
# 6. CONSISTENCY
# ==========================================

comparison = reports.merge(
    hospitals[
        ["Hospital_ID", "Hospital_Name", "District"]
    ],
    on="Hospital_ID",
    how="left",
    suffixes=("_report", "_master"),
    indicator=True
)

invalid_hospital_ids = (
    comparison["_merge"] == "left_only"
).sum()

name_mismatches = (
    comparison["_merge"].eq("both")
    & (
        comparison["Hospital_Name_report"].fillna("").str.strip().str.casefold()
        != comparison["Hospital_Name_master"].fillna("").str.strip().str.casefold()
    )
).sum()

district_mismatches = (
    comparison["_merge"].eq("both")
    & (
        comparison["District_report"].fillna("").str.strip().str.casefold()
        != comparison["District_master"].fillna("").str.strip().str.casefold()
    )
).sum()


# ==========================================
# 7. TIMELINESS
# ==========================================

status = reports["Report_Status"].astype(str).str.strip().str.casefold()
submission = reports["Submitted"].astype(str).str.strip().str.casefold()

on_time = (status == "on time").sum()
late = (status == "late").sum()
not_submitted = (submission == "no").sum()

submission_rate = (
    (submitted_count / total_records) * 100
    if total_records > 0 else 0
)

average_delay = submitted["Delay_Minutes"].mean()


# ==========================================
# 8. DISPLAY QUALITY SUMMARY
# ==========================================

print("\n========== DATA QUALITY SUMMARY ==========")

print("\nTOTAL RECORDS:", total_records)

print("\n1. COMPLETENESS")
print("Missing required values:", missing_values)
print(f"Completeness Score: {completeness_score:.2f}%")

print("\n2. VALIDITY")
print("Valid report dates:", valid_dates)
print("Valid case counts:", valid_cases)
print("Valid delay values:", valid_delays)
print(f"Validity Score: {validity_score:.2f}%")

print("\n3. UNIQUENESS")
print("Duplicate complete rows:", duplicate_rows)
print("Duplicate hospital-date reports:", duplicate_reports)

print("\n4. CONSISTENCY")
print("Invalid Hospital IDs:", invalid_hospital_ids)
print("Hospital name mismatches:", name_mismatches)
print("District mismatches:", district_mismatches)

print("\n5. TIMELINESS")
print("On-time reports:", on_time)
print("Late reports:", late)
print("Not submitted:", not_submitted)
print(f"Submission Rate: {submission_rate:.2f}%")

if pd.notna(average_delay):
    print(f"Average Delay: {average_delay:.2f} minutes")
else:
    print("Average Delay: No data available")

print("\n==========================================")
print("DATA QUALITY SUMMARY COMPLETED!")
