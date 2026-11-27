
import mysql.connector
from werkzeug.security import generate_password_hash

DB_PASSWORD = "Sahana@16"


def create_admin():

    connection = mysql.connector.connect(
        host="localhost",
        user="root",
        password=DB_PASSWORD,
        database="health_reporting_db"
    )

    cursor = connection.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin'"
    )

    if cursor.fetchone()[0] > 0:
        print("Administrator account already exists.")
        cursor.close()
        connection.close()
        return

    print("\n========== CREATE ADMIN ACCOUNT ==========\n")

    full_name = input("Enter full name: ").strip()
    username = input("Create username: ").strip()
    email = input("Enter email: ").strip()

    password = input("Create password: ")
    confirm_password = input("Confirm password: ")

    if not full_name or not username or not email:
        print("All fields are required.")
        return

    if len(password) < 8:
        print("Password must contain at least 8 characters.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    password_hash = generate_password_hash(password)

    cursor.execute(
        """
        INSERT INTO users
        (full_name, username, email, password_hash, role)
        VALUES (%s, %s, %s, %s, 'admin')
        """,
        (full_name, username, email, password_hash)
    )

    connection.commit()

    print("\nAdministrator account created successfully!")

    cursor.close()
    connection.close()


if __name__ == "__main__":
    try:
        create_admin()
    except Exception as e:
        print("\nERROR:", e)
