
import pandas as pd
import mysql.connector
from getpass import getpass

print("Starting Hospital Consistency Check...")

# 1. Connect to MySQL
connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Sahana@16",
    database="health_reporting_db"
)

print("Database connected successfully!")

# 2. Load both tables
reports = pd.read_sql(
    "SELECT * FROM health_reports",
    connection
)

hospitals = pd.read_sql(
    "SELECT * FROM hospitals",
    connection
)

connection.close()

print("Both tables loaded successfully!")

# 3. Compare report data with hospital master data
comparison = reports.merge(
    hospitals[["Hospital_ID", "Hospital_Name", "District"]],
    on="Hospital_ID",
    how="left",
    suffixes=("_report", "_master"),
    indicator=True
)

# 4. Find missing hospital IDs
invalid_hospital_ids = comparison[
    comparison["_merge"] == "left_only"
]

# 5. Find hospital name mismatches
name_mismatches = comparison[
    (comparison["_merge"] == "both") &
    (
        comparison["Hospital_Name_report"].str.strip().str.casefold()
        != comparison["Hospital_Name_master"].str.strip().str.casefold()
    )
]

# 6. Find district mismatches
district_mismatches = comparison[
    (comparison["_merge"] == "both") &
    (
        comparison["District_report"].str.strip().str.casefold()
        != comparison["District_master"].str.strip().str.casefold()
    )
]

# 7. Display results
print("\n========== HOSPITAL CONSISTENCY REPORT ==========")

print("\nTotal Health Reports:", len(reports))
print("Total Hospitals in Master Table:", len(hospitals))

print("\n1. INVALID HOSPITAL IDs:", len(invalid_hospital_ids))
print("2. HOSPITAL NAME MISMATCHES:", len(name_mismatches))
print("3. DISTRICT MISMATCHES:", len(district_mismatches))

print("\n=================================================")

print("\nCONSISTENCY CHECK COMPLETED!")
