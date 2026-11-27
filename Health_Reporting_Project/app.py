import os
import csv

from io import BytesIO, StringIO
from datetime import timedelta, datetime
from functools import wraps
from zoneinfo import ZoneInfo

import mysql.connector

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_file
)

from werkzeug.security import check_password_hash

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    LongTable,
    TableStyle
)


app = Flask(__name__)


# =====================================
# APPLICATION CONFIGURATION
# =====================================

app.secret_key = os.environ.get("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError(
        "FLASK_SECRET_KEY environment variable is not configured."
    )

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# =====================================
# DATABASE CONFIGURATION
# =====================================

DB_PASSWORD = "Sahana@16"

if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD environment variable is not configured."
    )


def get_connection():

    return mysql.connector.connect(
        host="localhost",
        user="root",
        password=DB_PASSWORD,
        database="health_reporting_db"
    )


# =====================================
# LOGIN PROTECTION
# =====================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect(url_for("login"))

        return function(*args, **kwargs)

    return wrapper


# =====================================
# LOGIN PAGE
# =====================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:

            flash("Please enter your username and password.")

            return render_template("login.html")

        connection = None
        cursor = None

        try:

            connection = get_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    user_id,
                    full_name,
                    username,
                    password_hash,
                    role,
                    hospital_id,
                    is_active
                FROM users
                WHERE username = %s
                LIMIT 1
            """, (username,))

            user = cursor.fetchone()

            if (
                user
                and user["is_active"]
                and check_password_hash(
                    user["password_hash"],
                    password
                )
            ):

                session.clear()

                session["user_id"] = user["user_id"]
                session["full_name"] = user["full_name"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                session["hospital_id"] = user["hospital_id"]

                session.permanent = True

                return redirect(url_for("home"))

            flash("Invalid username or password.")

        except mysql.connector.Error as error:

            print("LOGIN DATABASE ERROR:", error)

            flash(
                "Unable to connect to the database. Please try again."
            )

        finally:

            if cursor:
                cursor.close()

            if connection and connection.is_connected():
                connection.close()

    return render_template("login.html")


# =====================================
# LOGOUT
# =====================================

@app.route("/logout")
@login_required
def logout():

    session.clear()

    flash("You have successfully logged out.")

    return redirect(url_for("login"))


# =====================================
# GET DASHBOARD DATA
# =====================================

def get_dashboard_data():

    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:

        # 1. DASHBOARD SUMMARY

        cursor.execute("""
            SELECT
                COUNT(*) AS total_reports,

                SUM(
                    CASE WHEN Submitted = 'Yes'
                    THEN 1 ELSE 0 END
                ) AS submitted,

                SUM(
                    CASE WHEN Submitted = 'No'
                    THEN 1 ELSE 0 END
                ) AS not_submitted,

                SUM(
                    CASE WHEN Report_Status = 'On Time'
                    THEN 1 ELSE 0 END
                ) AS on_time,

                SUM(
                    CASE WHEN Report_Status = 'Late'
                    THEN 1 ELSE 0 END
                ) AS late

            FROM health_reports
        """)

        data = cursor.fetchone()

        for key in data:
            data[key] = data[key] or 0

        cursor.execute("""
            SELECT
                CAST(
                    COALESCE(SUM(Cases), 0)
                    AS UNSIGNED
                ) AS total_cases

            FROM health_reports
            WHERE Submitted = 'Yes'
        """)

        data["total_cases"] = cursor.fetchone()["total_cases"]

        total_records = data["total_reports"]
        submitted_count = data["submitted"]

        # 2. DISEASE-WISE CASES

        cursor.execute("""
            SELECT
                Disease AS label,
                CAST(SUM(Cases) AS UNSIGNED) AS total_cases

            FROM health_reports
            WHERE Submitted = 'Yes'

            GROUP BY Disease
            ORDER BY total_cases DESC
        """)

        disease_summary = cursor.fetchall()

        # 3. DISTRICT-WISE CASES

        cursor.execute("""
            SELECT
                District AS label,
                CAST(SUM(Cases) AS UNSIGNED) AS total_cases

            FROM health_reports
            WHERE Submitted = 'Yes'

            GROUP BY District
            ORDER BY total_cases DESC
        """)

        district_summary = cursor.fetchall()

        # 4. MONTHLY CASES

        cursor.execute("""
            SELECT
                DATE_FORMAT(Report_Date, '%Y-%m') AS label,

                CAST(SUM(Cases) AS UNSIGNED) AS total_cases

            FROM health_reports
            WHERE Submitted = 'Yes'

            GROUP BY DATE_FORMAT(Report_Date, '%Y-%m')
            ORDER BY label
        """)

        monthly_summary = cursor.fetchall()

        # 5. COMPLETENESS ANALYSIS

        cursor.execute("""
            SELECT

                COUNT(*) AS total_records,

                COALESCE(SUM(
                    CASE
                        WHEN Report_Date IS NULL
                        OR Hospital_ID IS NULL
                        OR Hospital_Name IS NULL
                        OR District IS NULL
                        OR Disease IS NULL
                        OR Submitted IS NULL
                        THEN 1 ELSE 0
                    END
                ), 0) AS missing_values

            FROM health_reports
        """)

        completeness_data = cursor.fetchone()

        missing_values = completeness_data["missing_values"] or 0

        completeness_score = (
            (
                (total_records * 6 - missing_values)
                / (total_records * 6)
            ) * 100
            if total_records > 0 else 0
        )

        # 6. EXPECTED VS UNEXPECTED MISSING VALUES

        cursor.execute("""
            SELECT

                COALESCE(SUM(
                    CASE
                        WHEN Submitted = 'No' THEN

                            (Cases IS NULL)

                            + (
                                Submission_Time IS NULL
                                OR TRIM(
                                    COALESCE(Submission_Time, '')
                                ) = ''
                            )

                            + (Delay_Minutes IS NULL)

                        ELSE 0
                    END
                ), 0) AS expected_missing_values,

                COALESCE(SUM(
                    CASE
                        WHEN Submitted = 'Yes' THEN

                            (Cases IS NULL)

                            + (
                                Submission_Time IS NULL
                                OR TRIM(
                                    COALESCE(Submission_Time, '')
                                ) = ''
                            )

                            + (Delay_Minutes IS NULL)

                        ELSE 0
                    END
                ), 0) AS unexpected_missing_values,

                COALESCE(SUM(
                    CASE
                        WHEN Submitted = 'Yes'
                        AND Cases IS NULL
                        THEN 1 ELSE 0
                    END
                ), 0) AS missing_cases_submitted,

                COALESCE(SUM(
                    CASE
                        WHEN Submitted = 'Yes'
                        AND (
                            Submission_Time IS NULL
                            OR TRIM(
                                COALESCE(Submission_Time, '')
                            ) = ''
                        )
                        THEN 1 ELSE 0
                    END
                ), 0) AS missing_submission_time_submitted,

                COALESCE(SUM(
                    CASE
                        WHEN Submitted = 'Yes'
                        AND Delay_Minutes IS NULL
                        THEN 1 ELSE 0
                    END
                ), 0) AS missing_delays_submitted

            FROM health_reports
        """)

        missing_data = cursor.fetchone()

        # 7. VALIDITY ANALYSIS

        cursor.execute("""
            SELECT

                COALESCE(SUM(
                    CASE
                        WHEN Report_Date IS NOT NULL
                        THEN 1 ELSE 0
                    END
                ), 0) AS valid_dates,

                COALESCE(SUM(
                    CASE
                        WHEN Submitted = 'Yes'
                        AND Cases IS NOT NULL
                        AND Cases >= 0
                        THEN 1 ELSE 0
                    END
                ), 0) AS valid_cases,

                COALESCE(SUM(
                    CASE
                        WHEN Submitted = 'Yes'
                        AND Delay_Minutes IS NOT NULL
                        AND Delay_Minutes >= 0
                        THEN 1 ELSE 0
                    END
                ), 0) AS valid_delays,

                COALESCE(SUM(
                    CASE
                        WHEN Submitted NOT IN ('Yes', 'No')
                        OR Submitted IS NULL
                        THEN 1 ELSE 0
                    END
                ), 0) AS invalid_submission_values,

                COALESCE(SUM(
                    CASE

                        WHEN Submitted = 'Yes'
                        AND Report_Status NOT IN ('On Time', 'Late')
                        THEN 1

                        WHEN Submitted = 'No'
                        AND Report_Status != 'Not Submitted'
                        THEN 1

                        WHEN Report_Status IS NULL
                        THEN 1

                        ELSE 0

                    END
                ), 0) AS status_mismatches

            FROM health_reports
        """)

        validity_data = cursor.fetchone()

        valid_dates = validity_data["valid_dates"]
        valid_cases = validity_data["valid_cases"]
        valid_delays = validity_data["valid_delays"]

        validity_denominator = total_records + (2 * submitted_count)

        validity_score = (
            (
                (valid_dates + valid_cases + valid_delays)
                / validity_denominator
            ) * 100
            if validity_denominator > 0 else 0
        )

        # 8. UNIQUENESS ANALYSIS

        cursor.execute("""
            SELECT
                COALESCE(
                    SUM(duplicate_count - 1), 0
                ) AS duplicate_reports

            FROM (
                SELECT COUNT(*) AS duplicate_count

                FROM health_reports

                GROUP BY Hospital_ID, Report_Date, Disease

                HAVING COUNT(*) > 1

            ) AS duplicates
        """)

        duplicate_reports = (
            cursor.fetchone()["duplicate_reports"] or 0
        )

        cursor.execute("""
            SELECT
                COALESCE(
                    SUM(duplicate_count - 1), 0
                ) AS duplicate_report_ids

            FROM (
                SELECT
                    COUNT(*) AS duplicate_count

                FROM duplicate_id_test_records

                GROUP BY Test_Report_ID

                HAVING COUNT(*) > 1

            ) AS duplicates
        """)

        duplicate_report_ids = (
                cursor.fetchone()["duplicate_report_ids"] or 0
        )
        # 9. CONSISTENCY ANALYSIS

        cursor.execute("""
            SELECT

                COALESCE(SUM(
                    CASE
                        WHEN h.Hospital_ID IS NULL
                        THEN 1 ELSE 0
                    END
                ), 0) AS invalid_hospital_ids,

                COALESCE(SUM(
                    CASE
                        WHEN h.Hospital_ID IS NOT NULL
                        AND LOWER(TRIM(r.Hospital_Name))
                            != LOWER(TRIM(h.Hospital_Name))
                        THEN 1 ELSE 0
                    END
                ), 0) AS name_mismatches,

                COALESCE(SUM(
                    CASE
                        WHEN h.Hospital_ID IS NOT NULL
                        AND LOWER(TRIM(r.District))
                            != LOWER(TRIM(h.District))
                        THEN 1 ELSE 0
                    END
                ), 0) AS district_mismatches

            FROM health_reports r

            LEFT JOIN hospitals h
                ON r.Hospital_ID = h.Hospital_ID
        """)

        consistency_data = cursor.fetchone()

        # 10. TIMELINESS ANALYSIS

        cursor.execute("""
            SELECT

                AVG(
                    CASE
                        WHEN Submitted = 'Yes'
                        THEN Delay_Minutes
                    END
                ) AS average_delay

            FROM health_reports
        """)

        average_delay = cursor.fetchone()["average_delay"]

        submission_rate = (
            submitted_count / total_records * 100
            if total_records > 0 else 0
        )

        # 11. FINAL QUALITY SUMMARY

        quality = {

            "completeness": round(completeness_score, 2),
            "validity": round(validity_score, 2),

            "missing_values": missing_values,

            "expected_missing_values":
                missing_data["expected_missing_values"],

            "unexpected_missing_values":
                missing_data["unexpected_missing_values"],

            "missing_cases_submitted":
                missing_data["missing_cases_submitted"],

            "missing_submission_time_submitted":
                missing_data["missing_submission_time_submitted"],

            "missing_delays_submitted":
                missing_data["missing_delays_submitted"],

            "valid_dates": valid_dates,
            "valid_cases": valid_cases,
            "valid_delays": valid_delays,

            "invalid_submission_values":
                validity_data["invalid_submission_values"],

            "status_mismatches":
                validity_data["status_mismatches"],

            "duplicate_reports": duplicate_reports,
            "duplicate_report_ids": duplicate_report_ids,

            "invalid_hospital_ids":
                consistency_data["invalid_hospital_ids"],

            "name_mismatches":
                consistency_data["name_mismatches"],

            "district_mismatches":
                consistency_data["district_mismatches"],

            "average_delay":
                round(float(average_delay), 2)
                if average_delay is not None else 0,

            "submission_rate": round(submission_rate, 2),

            "on_time": data["on_time"],
            "late": data["late"],
            "not_submitted": data["not_submitted"]
        }

        return {

            "summary": data,

            "disease_summary": disease_summary,

            "district_summary": district_summary,

            "monthly_summary": monthly_summary,

            "quality": quality

        }

    finally:

        cursor.close()
        connection.close()


# =====================================
# 1. OVERVIEW PAGE
# =====================================

@app.route("/")
@login_required
def home():

    dashboard = get_dashboard_data()

    return render_template(
        "dashboard.html",
        **dashboard
    )


# =====================================
# 2. DATA QUALITY PAGE
# =====================================

@app.route("/data-quality")
@login_required
def data_quality():

    dashboard = get_dashboard_data()

    return render_template(
        "data_quality.html",
        quality=dashboard["quality"]
    )


# =====================================
# 3. HOSPITAL PERFORMANCE PAGE
# =====================================

@app.route("/hospital-performance")
@login_required
def hospital_performance():

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:

        query = """

            SELECT

                h.Hospital_Name AS hospital_name,

                h.District AS district,

                COUNT(hr.Report_ID) AS total_reports,

                SUM(
                    CASE
                        WHEN hr.Report_Status IN ('On Time', 'Late')
                        THEN 1 ELSE 0
                    END
                ) AS submitted,

                SUM(
                    CASE
                        WHEN hr.Report_Status NOT IN ('On Time', 'Late')
                             OR hr.Report_Status IS NULL
                        THEN 1 ELSE 0
                    END
                ) AS not_submitted,

                SUM(
                    CASE
                        WHEN hr.Report_Status = 'On Time'
                        THEN 1 ELSE 0
                    END
                ) AS on_time,

                SUM(
                    CASE
                        WHEN hr.Report_Status = 'Late'
                        THEN 1 ELSE 0
                    END
                ) AS late,

                ROUND(

                    SUM(
                        CASE
                            WHEN hr.Report_Status IN ('On Time', 'Late')
                            THEN 1 ELSE 0
                        END
                    ) * 100.0 / NULLIF(COUNT(hr.Report_ID), 0),

                    2

                ) AS submission_rate,

                ROUND(
                    AVG(hr.Delay_Minutes), 2
                ) AS average_delay

            FROM hospitals h

            LEFT JOIN health_reports hr
                ON h.Hospital_ID = hr.Hospital_ID

            GROUP BY
                h.Hospital_ID,
                h.Hospital_Name,
                h.District

            ORDER BY h.Hospital_Name

        """

        cursor.execute(query)

        hospital_data = cursor.fetchall()

    finally:

        cursor.close()
        conn.close()

    return render_template(
        "hospital_performance.html",
        hospital_performance=hospital_data
    )


# =====================================
# 4. DISEASE ANALYSIS PAGE
# =====================================

@app.route("/disease-analysis")
@login_required
def disease_analysis():

    dashboard = get_dashboard_data()

    return render_template(
        "disease_analysis.html",

        disease_summary=dashboard["disease_summary"],

        district_summary=dashboard["district_summary"],

        monthly_summary=dashboard["monthly_summary"]
    )


# =====================================
# 5. SMART ALERTS
# =====================================

@app.route("/smart-alerts")
@login_required
def smart_alerts():

    connection = None
    cursor = None

    role = session.get("role")
    hospital_id = session.get("hospital_id")

    if role == "hospital_operator" and not hospital_id:

        flash(
            "No hospital is assigned to your account.",
            "error"
        )

        return redirect(url_for("home"))

    try:

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        parameters = ()
        hospital_condition = ""

        if role == "hospital_operator":

            hospital_condition = " AND Hospital_ID = %s "
            parameters = (hospital_id,)

        # A. LATE SUBMISSION ALERTS

        cursor.execute("""
            SELECT
                Report_ID,
                Report_Date,
                Hospital_ID,
                Hospital_Name,
                District,
                Disease,
                Delay_Minutes,
                Submission_Time,
                Report_Status

            FROM health_reports

            WHERE Report_Status = 'Late'
        """ + hospital_condition + """
            ORDER BY Report_Date DESC, Delay_Minutes DESC
            LIMIT 200
        """, parameters)

        late_reports = cursor.fetchall()

        # B. MISSING SUBMISSION ALERTS

        cursor.execute("""
            SELECT
                Report_ID,
                Report_Date,
                Hospital_ID,
                Hospital_Name,
                District,
                Disease,
                Report_Status

            FROM health_reports

            WHERE (
                Submitted = 'No'
                OR Report_Status = 'Not Submitted'
            )
        """ + hospital_condition + """
            ORDER BY Report_Date DESC
            LIMIT 200
        """, parameters)

        missing_reports = cursor.fetchall()

        # C. DISEASE INCREASE ALERTS

        cursor.execute("""
            SELECT
                Disease,
                DATE_FORMAT(Report_Date, '%Y-%m') AS report_month,
                SUM(Cases) AS total_cases

            FROM health_reports

            WHERE Submitted = 'Yes'
              AND Cases IS NOT NULL
        """ + hospital_condition + """
            GROUP BY
                Disease,
                DATE_FORMAT(Report_Date, '%Y-%m')

            ORDER BY report_month
        """, parameters)

        monthly_disease_data = cursor.fetchall()

        available_months = sorted({
            row["report_month"]
            for row in monthly_disease_data
            if row["report_month"]
        })

        disease_alerts = []

        if len(available_months) >= 2:

            previous_month = available_months[-2]
            latest_month = available_months[-1]

            disease_totals = {}

            for row in monthly_disease_data:

                disease = row["Disease"]
                month = row["report_month"]

                if disease not in disease_totals:
                    disease_totals[disease] = {}

                disease_totals[disease][month] = (
                    float(row["total_cases"] or 0)
                )

            for disease, monthly_totals in disease_totals.items():

                previous_cases = monthly_totals.get(
                    previous_month,
                    0
                )

                latest_cases = monthly_totals.get(
                    latest_month,
                    0
                )

                if previous_cases <= 0:
                    continue

                increase = (
                    (latest_cases - previous_cases)
                    / previous_cases
                ) * 100

                if increase >= 25:

                    disease_alerts.append({

                        "disease": disease,

                        "previous_month": previous_month,

                        "latest_month": latest_month,

                        "previous_cases": int(previous_cases),

                        "latest_cases": int(latest_cases),

                        "increase": round(increase, 2)

                    })

            disease_alerts.sort(
                key=lambda item: item["increase"],
                reverse=True
            )

        # D. ALERT SUMMARY

        alert_summary = {

            "late_count": len(late_reports),

            "missing_count": len(missing_reports),

            "disease_count": len(disease_alerts),

            "total_alerts": (
                len(late_reports)
                + len(missing_reports)
                + len(disease_alerts)
            )

        }

        return render_template(

            "smart_alerts.html",

            late_reports=late_reports,

            missing_reports=missing_reports,

            disease_alerts=disease_alerts,

            alert_summary=alert_summary,

            previous_month=(
                available_months[-2]
                if len(available_months) >= 2
                else None
            ),

            latest_month=(
                available_months[-1]
                if len(available_months) >= 1
                else None
            )

        )

    except mysql.connector.Error as error:

        print("SMART ALERTS DATABASE ERROR:", error)

        flash(
            "Unable to load smart alerts. Please try again.",
            "error"
        )

        return redirect(url_for("home"))

    finally:

        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()
# =====================================
# ADD REPORT PAGE HELPER
# =====================================

def render_add_report_page(cursor, role):

    if role == "hospital_operator":

        cursor.execute("""
            SELECT
                Hospital_ID,
                Hospital_Name,
                District
            FROM hospitals
            WHERE Hospital_ID = %s
        """, (session.get("hospital_id"),))

    else:

        cursor.execute("""
            SELECT
                Hospital_ID,
                Hospital_Name,
                District
            FROM hospitals
            ORDER BY Hospital_Name
        """)

    hospitals_list = cursor.fetchall()

    cursor.execute("""
        SELECT DISTINCT Disease
        FROM health_reports
        WHERE Disease IS NOT NULL
          AND TRIM(Disease) != ''
        ORDER BY Disease
    """)

    diseases_list = [
        row["Disease"] for row in cursor.fetchall()
    ]

    return render_template(
        "add_report.html",
        hospitals=hospitals_list,
        diseases=diseases_list
    )


# =====================================
# 6. ADD NEW REPORT
# =====================================

@app.route("/add-report", methods=["GET", "POST"])
@login_required
def add_report():

    role = session.get("role")

    if role not in ["admin", "hospital_operator"]:
        flash(
            "You do not have permission to add reports.",
            "error"
        )
        return redirect(url_for("home"))

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        if request.method == "GET":

            if (
                role == "hospital_operator"
                and not session.get("hospital_id")
            ):
                flash(
                    "No hospital is assigned to your account.",
                    "error"
                )
                return redirect(url_for("home"))

            return render_add_report_page(cursor, role)

        action = request.form.get("action", "").strip()

        report_date = request.form.get(
            "report_date", ""
        ).strip()

        hospital_id = request.form.get(
            "hospital_id", ""
        ).strip()

        disease = request.form.get(
            "disease", ""
        ).strip()

        cases_text = request.form.get(
            "cases", ""
        ).strip()

        submitted = request.form.get(
            "submitted", ""
        ).strip()

        remarks = request.form.get(
            "remarks", ""
        ).strip()

        # Submission time and delay are calculated
        # by the server, not accepted from the browser.
        submission_time = None
        delay_minutes = None

        # Hospital operators can submit only
        # for their assigned hospital.
        if role == "hospital_operator":

            hospital_id = session.get("hospital_id")

            if not hospital_id:
                flash(
                    "No hospital is assigned to your account.",
                    "error"
                )
                return redirect(url_for("home"))

        # VALIDATE CASE COUNT
        try:
            cases = int(cases_text) if cases_text else None

            if cases is not None and cases < 0:
                raise ValueError

        except ValueError:
            flash(
                "Please enter a valid non-negative number of cases.",
                "error"
            )
            return render_add_report_page(cursor, role)

        # SAVE AS DRAFT
        if action == "draft":

            if submitted not in ["Yes", "No"]:
                submitted = None

            if hospital_id:

                cursor.execute("""
                    SELECT Hospital_ID
                    FROM hospitals
                    WHERE Hospital_ID = %s
                """, (hospital_id,))

                if not cursor.fetchone():
                    flash(
                        "Invalid hospital selected.",
                        "error"
                    )
                    return render_add_report_page(cursor, role)

            if report_date:
                try:
                    datetime.strptime(
                        report_date,
                        "%Y-%m-%d"
                    )

                except ValueError:
                    flash(
                        "Please enter a valid report date.",
                        "error"
                    )
                    return render_add_report_page(cursor, role)

            # Drafts are not actual submissions.
            cursor.execute("""
                INSERT INTO report_drafts (
                    Report_Date,
                    Hospital_ID,
                    Disease,
                    Cases,
                    Submitted,
                    Submission_Time,
                    Delay_Minutes,
                    Remarks,
                    Created_By
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
            """, (
                report_date or None,
                hospital_id or None,
                disease or None,
                cases,
                submitted,
                None,
                None,
                remarks or None,
                session["user_id"]
            ))

            connection.commit()

            flash(
                "Your report has been saved as a draft.",
                "success"
            )

            return redirect(url_for("add_report"))

        # SUBMIT REPORT
        elif action == "submit":

            if not report_date:
                flash(
                    "Please select a report date.",
                    "error"
                )
                return render_add_report_page(cursor, role)

            if not hospital_id:
                flash(
                    "Please select a hospital.",
                    "error"
                )
                return render_add_report_page(cursor, role)

            if not disease:
                flash(
                    "Please select a disease.",
                    "error"
                )
                return render_add_report_page(cursor, role)

            if submitted not in ["Yes", "No"]:
                flash(
                    "Please select the submission status.",
                    "error"
                )
                return render_add_report_page(cursor, role)

            try:
                datetime.strptime(
                    report_date,
                    "%Y-%m-%d"
                )

            except ValueError:
                flash(
                    "Please enter a valid report date.",
                    "error"
                )
                return render_add_report_page(cursor, role)

            # VERIFY HOSPITAL
            cursor.execute("""
                SELECT
                    Hospital_ID,
                    Hospital_Name,
                    District
                FROM hospitals
                WHERE Hospital_ID = %s
            """, (hospital_id,))

            hospital = cursor.fetchone()

            if not hospital:
                flash(
                    "Invalid hospital selected.",
                    "error"
                )
                return render_add_report_page(cursor, role)

            # IF REPORT IS SUBMITTED
            if submitted == "Yes":

                if cases is None:
                    flash(
                        "Please enter the number of cases.",
                        "error"
                    )
                    return render_add_report_page(cursor, role)

                # GET MANUALLY ENTERED SUBMISSION TIME
                entered_time = request.form.get(
                    "submission_time", ""
                ).strip()

                if not entered_time:
                    flash(
                        "Please enter the submission time.",
                        "error"
                    )
                    return render_add_report_page(cursor, role)

                try:
                    entered_time = datetime.strptime(
                        entered_time,
                        "%H:%M"
                    ).time()

                except ValueError:
                    flash(
                        "Please enter a valid submission time.",
                        "error"
                    )
                    return render_add_report_page(cursor, role)

                submission_time = entered_time.strftime("%H:%M:%S")

                # USE THE SELECTED REPORT DATE
                report_day = datetime.strptime(
                    report_date,
                    "%Y-%m-%d"
                ).date()

                # COMBINE REPORT DATE AND SUBMISSION TIME
                submitted_at = datetime.combine(
                    report_day,
                    entered_time
                )

                # DAILY DEADLINE: 8:00 PM
                deadline = datetime.combine(
                    report_day,
                    datetime.strptime(
                        "20:00",
                        "%H:%M"
                    ).time()
                )

                # AUTOMATIC DELAY CALCULATION
                seconds_late = max(
                    0,
                    (submitted_at - deadline).total_seconds()
                )

                delay_minutes = int(
                    (seconds_late + 59) // 60
                )

                # AUTOMATIC REPORT STATUS
                report_status = (
                    "On Time"
                    if delay_minutes == 0
                    else "Late"
                )

            # IF REPORT IS NOT SUBMITTED
            else:
                cases = None
                submission_time = None
                delay_minutes = None

                report_status = "Not Submitted"

            # DUPLICATE REPORT DETECTION
            cursor.execute("""
                SELECT Report_ID
                FROM health_reports
                WHERE Hospital_ID = %s
                  AND Report_Date = %s
                  AND Disease = %s
                LIMIT 1
            """, (
                hospital_id,
                report_date,
                disease
            ))

            duplicate = cursor.fetchone()

            if duplicate:
                flash(
                    "A report for this hospital, date and disease already exists.",
                    "error"
                )
                return render_add_report_page(cursor, role)

            # INSERT REPORT INTO DATABASE
            cursor.execute("""
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
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
            """, (
                report_date,
                hospital["Hospital_ID"],
                hospital["Hospital_Name"],
                hospital["District"],
                disease,
                cases,
                submitted,
                submission_time,
                remarks or None,
                report_status,
                delay_minutes
            ))

            connection.commit()

            flash(
                "Report submitted successfully!",
                "success"
            )

            return redirect(url_for("add_report"))

        else:
            flash(
                "Invalid form action.",
                "error"
            )
            return render_add_report_page(cursor, role)

    except mysql.connector.Error as error:

        if connection and connection.is_connected():
            connection.rollback()

        print("ADD REPORT DATABASE ERROR:", error)

        flash(
            "A database error occurred. Please try again.",
            "error"
        )

        return redirect(url_for("add_report"))

    finally:

        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()

# =====================================
# 7. EXPORT REPORTS - OPTIMIZED
# =====================================

@app.route("/export/<file_format>")
@login_required
def export_reports(file_format):

    if file_format not in ["excel", "csv", "pdf"]:

        flash("Invalid export format.", "error")

        return redirect(url_for("home"))

    role = session.get("role")

    if role not in [
        "admin",
        "hospital_operator",
        "analyst"
    ]:

        flash(
            "You do not have permission to export reports.",
            "error"
        )

        return redirect(url_for("home"))

    connection = None
    cursor = None

    try:

        connection = get_connection()

        cursor = connection.cursor(
            dictionary=True,
            buffered=False
        )

        query = """
            SELECT
                Report_ID,
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

            FROM health_reports
        """

        parameters = ()

        if role == "hospital_operator":

            hospital_id = session.get("hospital_id")

            if not hospital_id:

                flash(
                    "No hospital is assigned to your account.",
                    "error"
                )

                return redirect(url_for("home"))

            query += " WHERE Hospital_ID = %s"

            parameters = (hospital_id,)

        query += " ORDER BY Report_Date DESC, Report_ID DESC"

        cursor.execute(query, parameters)

        headers = [
            "Report ID",
            "Report Date",
            "Hospital ID",
            "Hospital Name",
            "District",
            "Disease",
            "Cases",
            "Submitted",
            "Submission Time",
            "Remarks",
            "Report Status",
            "Delay Minutes"
        ]

        columns = [
            "Report_ID",
            "Report_Date",
            "Hospital_ID",
            "Hospital_Name",
            "District",
            "Disease",
            "Cases",
            "Submitted",
            "Submission_Time",
            "Remarks",
            "Report_Status",
            "Delay_Minutes"
        ]
        def safe_value(value):

            if value is None:
                return ""

            if isinstance(value, str) and value.startswith(
                ("=", "+", "-", "@", "\t", "\r")
            ):

                return "'" + value

            return value

        # =====================================
        # EXPORT AS EXCEL
        # =====================================

        if file_format == "excel":

            workbook = Workbook(write_only=True)

            worksheet = workbook.create_sheet(
                title="Health Reports"
            )

            worksheet.freeze_panes = "A2"

            widths = [
                14, 16, 14, 25, 20, 25,
                12, 14, 18, 30, 18, 16
            ]

            for index, width in enumerate(widths, start=1):

                column_letter = get_column_letter(index)

                worksheet.column_dimensions[
                    column_letter
                ].width = width

            header_row = []

            for heading in headers:

                cell = WriteOnlyCell(
                    worksheet,
                    value=heading
                )

                cell.font = Font(
                    bold=True,
                    color="FFFFFF"
                )

                cell.fill = PatternFill(
                    start_color="1B1931",
                    end_color="1B1931",
                    fill_type="solid"
                )

                cell.alignment = Alignment(
                    horizontal="center"
                )

                header_row.append(cell)

            worksheet.append(header_row)

            row_count = 0

            while True:

                batch = cursor.fetchmany(1000)

                if not batch:
                    break

                for report in batch:

                    row = [
                        safe_value(report.get(column))
                        for column in columns
                    ]

                    worksheet.append(row)

                    row_count += 1

            worksheet.auto_filter.ref = (
                f"A1:L{row_count + 1}"
            )

            output = BytesIO()

            workbook.save(output)

            output.seek(0)

            return send_file(
                output,
                as_attachment=True,
                download_name="health_reports.xlsx",
                mimetype=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                )
            )

        # =====================================
        # EXPORT AS CSV
        # =====================================

        elif file_format == "csv":

            output = StringIO()

            writer = csv.writer(output)

            writer.writerow(headers)

            while True:

                batch = cursor.fetchmany(1000)

                if not batch:
                    break

                for report in batch:

                    row = [
                        safe_value(report.get(column))
                        for column in columns
                    ]

                    writer.writerow(row)

            csv_output = BytesIO(
                output.getvalue().encode("utf-8-sig")
            )

            output.close()

            csv_output.seek(0)

            return send_file(
                csv_output,
                as_attachment=True,
                download_name="health_reports.csv",
                mimetype="text/csv"
            )

        # =====================================
        # EXPORT AS PDF
        # =====================================

        elif file_format == "pdf":

            output = BytesIO()

            document = SimpleDocTemplate(
                output,
                pagesize=landscape(A3),
                rightMargin=25,
                leftMargin=25,
                topMargin=30,
                bottomMargin=30
            )

            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                "ReportTitle",
                parent=styles["Title"],
                textColor=colors.HexColor("#1B1931"),
                alignment=TA_CENTER,
                fontSize=19,
                spaceAfter=12
            )

            story = []

            story.append(
                Paragraph(
                    "Health Reporting System",
                    title_style
                )
            )

            story.append(
                Paragraph(
                    "Hospital Health Reports",
                    styles["Heading2"]
                )
            )

            story.append(Spacer(1, 15))

            table_data = [headers]

            row_count = 0

            while True:

                batch = cursor.fetchmany(1000)

                if not batch:
                    break

                for report in batch:

                    row = []

                    for column in columns:

                        value = report.get(column)

                        if value is None:
                            value = "-"

                        else:
                            value = str(value)

                        row.append(value)

                    table_data.append(row)

                    row_count += 1

            story.append(
                Paragraph(
                    f"Total Records: {row_count}",
                    styles["Normal"]
                )
            )

            story.append(Spacer(1, 12))

            report_table = LongTable(
                table_data,
                colWidths=[
                    48, 65, 48, 105, 70, 90,
                    40, 50, 65, 125, 65, 55
                ],
                repeatRows=1,
                hAlign="LEFT"
            )

            report_table.setStyle(
                TableStyle([

                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, 0),
                        colors.HexColor("#1B1931")
                    ),

                    (
                        "TEXTCOLOR",
                        (0, 0),
                        (-1, 0),
                        colors.white
                    ),

                    (
                        "FONTNAME",
                        (0, 0),
                        (-1, 0),
                        "Helvetica-Bold"
                    ),

                    (
                        "FONTSIZE",
                        (0, 0),
                        (-1, -1),
                        6
                    ),

                    (
                        "GRID",
                        (0, 0),
                        (-1, -1),
                        0.4,
                        colors.HexColor("#E9BCB9")
                    ),

                    (
                        "VALIGN",
                        (0, 0),
                        (-1, -1),
                        "TOP"
                    ),

                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [
                            colors.white,
                            colors.HexColor("#FAF7F5")
                        ]
                    ),

                    (
                        "LEFTPADDING",
                        (0, 0),
                        (-1, -1),
                        4
                    ),

                    (
                        "RIGHTPADDING",
                        (0, 0),
                        (-1, -1),
                        4
                    ),

                    (
                        "TOPPADDING",
                        (0, 0),
                        (-1, -1),
                        5
                    ),

                    (
                        "BOTTOMPADDING",
                        (0, 0),
                        (-1, -1),
                        5
                    )

                ])
            )

            story.append(report_table)

            document.build(story)

            output.seek(0)

            return send_file(
                output,
                as_attachment=True,
                download_name="health_reports.pdf",
                mimetype="application/pdf"
            )

    except mysql.connector.Error as error:

        print("EXPORT DATABASE ERROR:", error)

        flash(
            "Unable to export reports. Please try again.",
            "error"
        )

        return redirect(url_for("home"))

    except Exception as error:

        print("EXPORT ERROR:", error)

        flash(
            "An error occurred while generating the export.",
            "error"
        )

        return redirect(url_for("home"))

    finally:

        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# =====================================
# 8. DISTRICT-WISE HEALTH MAP
# =====================================

@app.route("/district-map")
@login_required
def district_map():

    connection = None
    cursor = None

    # District centre coordinates for the 13 districts
    # supplied from your hospitals table.

    district_locations = {
        "Anantapuramu": [14.6819, 77.6006],
        "Annamayya": [14.0500, 78.7500],
        "Chittoor": [13.2172, 79.1003],
        "Eluru": [16.7107, 81.0952],
        "Guntur": [16.3067, 80.4365],
        "Krishna": [16.6100, 80.9500],
        "Kurnool": [15.8281, 78.0373],
        "NTR": [16.5062, 80.6480],
        "Prakasam": [15.5057, 80.0499],
        "SPSR Nellore": [14.4426, 79.9865],
        "Tirupati": [13.6288, 79.4192],
        "Visakhapatnam": [17.6868, 83.2185],
        "YSR Kadapa": [14.4673, 78.8242]
    }

    known_districts = [
        "Anantapuramu",
        "Annamayya",
        "Chittoor",
        "Eluru",
        "Guntur",
        "Krishna",
        "Kurnool",
        "NTR",
        "Prakasam",
        "SPSR Nellore",
        "Tirupati",
        "Visakhapatnam",
        "YSR Kadapa"
    ]

    try:

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                h.District AS district,

                COUNT(DISTINCT h.Hospital_ID)
                    AS hospital_count,

                COALESCE(
                    SUM(
                        CASE
                            WHEN hr.Submitted = 'Yes'
                            THEN hr.Cases
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_cases,

                COUNT(
                    DISTINCT CASE
                        WHEN hr.Submitted = 'Yes'
                        THEN hr.Report_ID
                    END
                ) AS submitted_reports

            FROM hospitals h

            LEFT JOIN health_reports hr
                ON h.Hospital_ID = hr.Hospital_ID

            WHERE h.State = %s
        """

        parameters = ["Andhra Pradesh"]

        if session.get("role") == "hospital_operator":

            query += " AND h.Hospital_ID = %s"

            parameters.append(
                session.get("hospital_id")
            )

        query += """
            GROUP BY h.District
            ORDER BY h.District
        """

        cursor.execute(
            query,
            tuple(parameters)
        )

        district_rows = cursor.fetchall()

        row_lookup = {
            row["district"]: row
            for row in district_rows
        }

        districts = []

        for district in known_districts:

            row = row_lookup.get(district, {})

            coordinates = district_locations[district]

            districts.append({

                "district": district,

                "hospital_count": int(
                    row.get("hospital_count") or 0
                ),

                "total_cases": int(
                    row.get("total_cases") or 0
                ),

                "submitted_reports": int(
                    row.get("submitted_reports") or 0
                ),

                "latitude": coordinates[0],

                "longitude": coordinates[1]

            })

        total_cases = sum(
            item["total_cases"]
            for item in districts
        )

        total_hospitals = sum(
            item["hospital_count"]
            for item in districts
        )

        return render_template(
            "district_map.html",
            districts=districts,
            total_cases=total_cases,
            total_hospitals=total_hospitals
        )

    except mysql.connector.Error as error:

        print("DISTRICT MAP DATABASE ERROR:", error)

        flash(
            "Unable to load district-wise health map. Please try again."
        )

        return redirect(url_for("home"))

    finally:

        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


# =====================================
# RUN FLASK APPLICATION
# =====================================

if __name__ == "__main__":

    app.run(
        debug=True,
        use_reloader=False
    )