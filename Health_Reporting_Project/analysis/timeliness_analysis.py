
import pandas as pd
import mysql.connector
from getpass import getpass

print("Starting Health Report Timeliness Analysis...")

# 1. Connect to MySQL
connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Sahana@16",
    database="health_reporting_db"
)

print("Database connected successfully!")

# 2. Load health reports
df = pd.read_sql(
    "SELECT * FROM health_reports",
    connection
)

connection.close()

print("Health reports loaded successfully!")

# 3. Clean submission status
df["Submitted"] = df["Submitted"].astype(str).str.strip()

# 4. Count submission categories
on_time = (df["Report_Status"].str.strip().str.casefold() == "on time").sum()
late = (df["Report_Status"].str.strip().str.casefold() == "late").sum()
not_submitted = (df["Submitted"].str.casefold() == "no").sum()

submitted_count = (df["Submitted"].str.casefold() == "yes").sum()

# 5. Calculate average delay for submitted reports
submitted_reports = df[
    df["Submitted"].str.casefold() == "yes"
]

average_delay = submitted_reports["Delay_Minutes"].mean()

# 6. Calculate submission rate
total_reports = len(df)

submission_rate = (
    submitted_count / total_reports * 100
    if total_reports > 0 else 0
)

# 7. Display overall results
print("\n========== TIMELINESS ANALYSIS REPORT ==========")

print("\nTOTAL REPORTS:", total_reports)

print("\nSUBMISSION PERFORMANCE")
print("Submitted Reports:", submitted_count)
print("Not Submitted Reports:", not_submitted)
print(f"Submission Rate: {submission_rate:.2f}%")

print("\nTIMELINESS")
print("On-Time Reports:", on_time)
print("Late Reports:", late)

if pd.notna(average_delay):
    print(f"Average Delay: {average_delay:.2f} minutes")
else:
    print("Average Delay: No data available")

# 8. Hospital-wise submission performance
hospital_performance = df.groupby(
    ["Hospital_ID", "Hospital_Name"]
).agg(
    Total_Reports=("Report_ID", "count"),
    Submitted_Reports=("Submitted", lambda x: (x.str.casefold() == "yes").sum()),
    Not_Submitted=("Submitted", lambda x: (x.str.casefold() == "no").sum())
).reset_index()

hospital_performance["Submission_Rate"] = (
    hospital_performance["Submitted_Reports"]
    / hospital_performance["Total_Reports"] * 100
)

print("\nHOSPITAL-WISE PERFORMANCE (FIRST 10)")
print(
    hospital_performance.head(10).to_string(index=False)
)

print("\n================================================")
print("TIMELINESS ANALYSIS COMPLETED!")
