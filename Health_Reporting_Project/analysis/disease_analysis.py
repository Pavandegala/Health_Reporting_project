
import pandas as pd
import mysql.connector
from getpass import getpass

print("Starting Disease-wise Health Analysis...")

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

# 3. Keep only submitted reports
df = df[df["Submitted"].str.strip().str.casefold() == "yes"].copy()

# 4. Convert report date
df["Report_Date"] = pd.to_datetime(
    df["Report_Date"],
    errors="coerce"
)

# 5. Disease-wise total cases
disease_summary = df.groupby("Disease").agg(
    Total_Cases=("Cases", "sum"),
    Total_Reports=("Report_ID", "count")
).reset_index()

disease_summary = disease_summary.sort_values(
    by="Total_Cases",
    ascending=False
)

# 6. District-wise total cases
district_summary = df.groupby("District").agg(
    Total_Cases=("Cases", "sum")
).reset_index()

district_summary = district_summary.sort_values(
    by="Total_Cases",
    ascending=False
)

# 7. Monthly total cases
df["Month"] = df["Report_Date"].dt.to_period("M").astype(str)

monthly_summary = df.groupby("Month").agg(
    Total_Cases=("Cases", "sum")
).reset_index()

monthly_summary = monthly_summary.sort_values("Month")

# 8. Display results
print("\n========== DISEASE-WISE HEALTH REPORT ==========")

print("\nTOTAL SUBMITTED REPORTS:", len(df))
print("TOTAL REPORTED CASES:", int(df["Cases"].sum()))

print("\n1. DISEASE-WISE CASE SUMMARY")
print(disease_summary.to_string(index=False))

print("\n2. DISTRICT-WISE CASE SUMMARY")
print(district_summary.to_string(index=False))

print("\n3. MONTHLY CASE SUMMARY")
print(monthly_summary.to_string(index=False))

print("\n================================================")
print("DISEASE ANALYSIS COMPLETED!")
