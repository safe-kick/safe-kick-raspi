import app.state as state


class SessionManager:
    @staticmethod
    def start(session_id: int, kickboard_id: str, user_id: int):
        state.current_session["session"]["session_id"] = session_id
        state.current_session["session"]["kickboard_id"] = kickboard_id
        state.current_session["session"]["user_id"] = user_id
        state.current_session["session"]["active"] = True

        state.current_session["device"]["is_locked"] = False
        state.current_session["device"]["status"] = "normal"

        state.current_session["warning"]["current_reason"] = None
        state.current_session["warning"]["count"] = 0
        state.current_session["warning"]["reasons"] = []
        state.current_session["warning"]["is_two_person"] = False
        state.current_session["warning"]["is_drunk"] = False

    @staticmethod
    def end():
        state.current_session["session"]["active"] = False
        state.current_session["device"]["is_locked"] = True
        state.current_session["device"]["status"] = "ended"

        state.current_session["session"]["session_id"] = None
        state.current_session["session"]["kickboard_id"] = None
        state.current_session["session"]["user_id"] = None

        state.current_session["warning"]["current_reason"] = None
        state.current_session["warning"]["is_two_person"] = False
        state.current_session["warning"]["is_drunk"] = False

    @staticmethod
    def lock(reason: str):
        state.current_session["device"]["is_locked"] = True
        state.current_session["device"]["status"] = "warning" if reason != "user" else "ended"
        state.current_session["warning"]["current_reason"] = reason

        if reason != "user":
            state.current_session["warning"]["count"] += 1

            if reason not in state.current_session["warning"]["reasons"]:
                state.current_session["warning"]["reasons"].append(reason)

            if reason == "two_person":
                state.current_session["warning"]["is_two_person"] = True

            if reason == "drunk":
                state.current_session["warning"]["is_drunk"] = True

    @staticmethod
    def unlock():
        state.current_session["device"]["is_locked"] = False
        state.current_session["device"]["status"] = "unlocked"
        state.current_session["warning"]["current_reason"] = None

    @staticmethod
    def update_face_score(score: float):
        state.current_session["sensor"]["face_score"] = score

    @staticmethod
    def update_weight(weight: float):
        state.current_session["sensor"]["weight"] = weight

    @staticmethod
    def update_gas(gas: float):
        state.current_session["sensor"]["gas"] = gas

    @staticmethod
    def get_session_id():
        return state.current_session["session"]["session_id"]

    @staticmethod
    def is_active():
        return state.current_session["session"]["active"]

    @staticmethod
    def is_locked():
        return state.current_session["device"]["is_locked"]

    @staticmethod
    def get_warning_count():
        return state.current_session["warning"]["count"]

    @staticmethod
    def get_stream_data():
        return {
            "face_score": state.current_session["sensor"]["face_score"],
            "weight": state.current_session["sensor"]["weight"],
            "gas": state.current_session["sensor"]["gas"],
            "is_two_person": state.current_session["warning"]["is_two_person"],
            "is_drunk": state.current_session["warning"]["is_drunk"],
            "is_locked": state.current_session["device"]["is_locked"],
            "status": state.current_session["device"]["status"],
            "warning_reason": state.current_session["warning"]["current_reason"],
        }

    @staticmethod
    def get_sensor_data():
        return {
            "face_score": state.current_session["sensor"]["face_score"],
            "weight": state.current_session["sensor"]["weight"],
            "gas": state.current_session["sensor"]["gas"],
        }