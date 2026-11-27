import mysql.connector
from werkzeug.security import check_password_hash

connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="Sahana@16",
    database="health_reporting_db"
)

cursor = connection.cursor()

cursor.execute("""
    SELECT password_hash
    FROM users
    WHERE username = %s
""", ("Sahana7",))

result = cursor.fetchone()

if result:
    stored_hash = result[0]

    test_password = input("Enter a password to test: ")

    if check_password_hash(stored_hash, test_password):
        print("PASSWORD MATCHED")
    else:
        print("PASSWORD REJECTED")

else:
    print("User not found")

cursor.close()
connection.close()