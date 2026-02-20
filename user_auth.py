
import hashlib

import user_store

class UserAuth:
    @staticmethod
    def verify_user(username: str, password: str) -> str | None:
        users = user_store.get_all_users()
        for user in users:
            if user["username"] == username and user["password"] == password:
                return user["role"]
            stored_password = user.get("password", "")
            if stored_password.startswith("sha256:"):
                stored_hash = stored_password.split(":", 1)[1]
                password_hash = hashlib.sha256(password.encode()).hexdigest()
                if user["username"] == username and stored_hash == password_hash:
                    return user["role"]
        return None

# For backward compatibility
verify_user = UserAuth.verify_user
