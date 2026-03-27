from auth import UserManager

class UserAuth:
    @staticmethod
    def verify_user(username: str, password: str) -> str | None:
        return UserManager.verify_user(username, password)

    @staticmethod
    def get_user_profile(username: str) -> dict | None:
        return UserManager.get_user_profile(username)

# For backward compatibility
verify_user = UserAuth.verify_user
get_user_profile = UserAuth.get_user_profile
