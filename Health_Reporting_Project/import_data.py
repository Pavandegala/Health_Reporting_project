
import csv
import mysql.connector
from pathlib import Path
from getpass import getpass

# CSV file location
csv_file = Path(__file__).parent / "Hospital_Dataset_Cleaned.csv"

# MySQL connection details
mysql_user = "root"
mysql_password = "Sahana@16"

# Connect to MySQL
connection = mysql.connector.connect(
    host="localhost",
    user=mysql_user,
    password=mysql_password,
    database="health_reporting_db"
)

cursor = connection.cursor()

try:
    # Check existing records
    cursor.execute("SELECT COUNT(*) FROM health_reports")
    existing_records = cursor.fetchone()[0]

    if existing_records > 0:
        print("Import stopped: Table already contains records.")
        print("Existing records:", existing_records)
        raise SystemExit

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    # SQL insert query
    insert_query = """
        INSERT INTO health_reports (
            Report_Date,
            Hospital_ID,
            Hospital_Name,
            District,
            Disease,
            Cases,
            Submitted,
            Submission_Time,
            Remarks,
            Report_Status,
            Delay_Minutes
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    batch = []
    total_inserted = 0


    def nullable_integer(value):
        value = value.strip()

        if value == "" or value == r"\N":
            return None

        number = float(value)

        if not number.is_integer():
            raise ValueError(f"Expected a whole number, got: {value}")

        return int(number)


    # Read CSV
    with open(csv_file, "r", newline="", encoding="utf-8-sig") as file:

        reader = csv.DictReader(file)

        for row in reader:

            record = (
                row["Date"],
                row["Hospital_ID"],
                row["Hospital_Name"],
                row["District"],
                row["Disease"],
                nullable_integer(row["Cases"]),
                row["Submitted"],
                row["Submission_Time"],
                row["Remarks"],
                row["Report_Status"],
                nullable_integer(row["Delay_Minutes"])
            )

            batch.append(record)

            if len(batch) == 1000:
                cursor.executemany(insert_query, batch)
                total_inserted += len(batch)
                batch.clear()

        if batch:
            cursor.executemany(insert_query, batch)
            total_inserted += len(batch)

    # Save records
    connection.commit()

    print("\nImport successful!")
    print("Total records imported:", total_inserted)

except Exception as error:
    connection.rollback()
    print("\nImport failed:", error)

finally:
    cursor.close()
    connection.close()
