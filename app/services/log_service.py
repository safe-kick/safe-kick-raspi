from app.db import get_connection


def save_sensor_log(session_id: int, face_score: float, weight: float, gas: float):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO sensor_logs (
            session_id,
            face_score,
            weight,
            gas
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            session_id,
            face_score,
            weight,
            gas
        )
    )

    conn.commit()
    conn.close()


def save_warning_log(session_id: int, warning_type: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO warning_logs (
            session_id,
            warning_type
        )
        VALUES (?, ?)
        """,
        (
            session_id,
            warning_type
        )
    )

    conn.commit()
    conn.close()