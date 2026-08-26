import app.state as state


class SessionManager:
    @staticmethod
    def start(session_id: int, kickboard_id: str, user_id: int):
        state.current_session["session"]["session_id"] = session_id
        state.current_session["session"]["kickboard_id"] = kickboard_id
        state.current_session["session"]["user_id"] = user_id
        state.current_session["session"]["active"] = True

        state.current_session["device"]["is_locked"] = True
        state.current_session["device"]["status"] = "waiting_auth"

        state.current_session["sensor"]["helmet_verified"] = False
        state.current_session["sensor"]["helmet_score"] = 0.0
        state.current_session["sensor"]["face_score"] = 0.0

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

        state.current_session["sensor"]["helmet_verified"] = False
        state.current_session["sensor"]["helmet_score"] = 0.0
        state.current_session["sensor"]["face_score"] = 0.0

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
        state.current_session["warning"]["is_two_person"] = False

    @staticmethod
    def confirm_locked(status: str = "locked"):
        state.current_session["device"]["is_locked"] = True
        state.current_session["device"]["status"] = status

    @staticmethod
    def warn_two_person():
        state.current_session["device"]["status"] = "warning"
        state.current_session["warning"]["current_reason"] = "two_person"
        state.current_session["warning"]["is_two_person"] = True
        state.current_session["warning"]["count"] += 1
        if "two_person" not in state.current_session["warning"]["reasons"]:
            state.current_session["warning"]["reasons"].append("two_person")

    @staticmethod
    def clear_warning():
        state.current_session["device"]["status"] = "unlocked"
        state.current_session["warning"]["current_reason"] = None
        state.current_session["warning"]["is_two_person"] = False

    @staticmethod
    def set_safety_state(safety_state: str):
        state.current_session["device"]["safety_state"] = safety_state

    @staticmethod
    def set_stm32_connected(connected: bool):
        state.current_session["device"]["stm32_connected"] = connected

    @staticmethod
    def update_face_score(score: float):
        state.current_session["sensor"]["face_score"] = score

    @staticmethod
    def update_helmet_status(verified: bool, score: float):
        state.current_session["sensor"]["helmet_verified"] = verified
        state.current_session["sensor"]["helmet_score"] = score

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
    def get_user_id():
        return state.current_session["session"]["user_id"]

    @staticmethod
    def is_active():
        return state.current_session["session"]["active"]

    @staticmethod
    def is_locked():
        return state.current_session["device"]["is_locked"]

    @staticmethod
    def is_identity_verified():
        return (
            state.current_session["sensor"]["face_score"] > 0
            and state.current_session["sensor"]["helmet_verified"] is True
        )

    @staticmethod
    def get_warning_count():
        return state.current_session["warning"]["count"]

    @staticmethod
    def get_warning_reasons():
        return list(state.current_session["warning"]["reasons"])

    @staticmethod
    def get_stream_data():
        return {
            "face_score": state.current_session["sensor"]["face_score"],
            "helmet_verified": state.current_session["sensor"]["helmet_verified"],
            "helmet_score": state.current_session["sensor"]["helmet_score"],
            "weight": state.current_session["sensor"]["weight"],
            "gas": state.current_session["sensor"]["gas"],
            "is_two_person": state.current_session["warning"]["is_two_person"],
            "is_drunk": state.current_session["warning"]["is_drunk"],
            "is_locked": state.current_session["device"]["is_locked"],
            "status": state.current_session["device"]["status"],
            "warning_reason": state.current_session["warning"]["current_reason"],
            "safety_state": state.current_session["device"]["safety_state"],
            "stm32_connected": state.current_session["device"]["stm32_connected"],
        }

    @staticmethod
    def get_device_data():
        return dict(state.current_session["device"])

    @staticmethod
    def get_sensor_data():
        return {
            "face_score": state.current_session["sensor"]["face_score"],
            "helmet_verified": state.current_session["sensor"]["helmet_verified"],
            "helmet_score": state.current_session["sensor"]["helmet_score"],
            "weight": state.current_session["sensor"]["weight"],
            "gas": state.current_session["sensor"]["gas"],
        }
