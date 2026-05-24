import getpass
import os
from garminconnect import Garmin
from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectConnectionError, GarminConnectTooManyRequestsError
class GarminService:

    def __init__(self, config):
        self.user_email = config.user_email
        self.user_password = config.user_password
        self.token_directory = os.path.join(os.getcwd(), ".garmin_tokens")
        self.client = None

    def _is_running_in_docker(self):
        """Detects if the application is running inside a Docker container."""
        return os.path.exists('/.dockerenv') or os.path.exists('/.dockerinit')

    def interactive_login(self):
        print("No credentials found — logging in interactively.")
        email = input("Enter your Garmin Connect email: ").strip()
        password = getpass.getpass("Enter your Garmin Connect password: ").strip()
        self._do_login(Garmin(email, password, prompt_mfa=self._get_mfa_code))

    def _get_mfa_code(self):
        """Prompts the user to enter the MFA code sent to their device."""
        return input("Enter the MFA code sent to your device: ")

    def _do_login(self, client:Garmin):
        client.login(self.token_directory)
        self.client = client

    def login(self):
        # First, try to login using saved tokens
        try:
            self._do_login(Garmin())
            print("Logged in using saved tokens.")
            return
        except GarminConnectTooManyRequestsError:
            print("Too many requests. Please wait before trying again.")
            raise
        except (GarminConnectAuthenticationError, GarminConnectConnectionError):
            print("No valid tokens found — falling back to credential login.")

        # If token-based login fails try to login using credentials
        if self.user_email and self.user_password:
            self._do_login(Garmin(self.user_email, self.user_password, prompt_mfa=self._get_mfa_code))
            print("Logged in using credentials.")
            return
            
        # If we're running in Docker, we won't be able to do interactive login, so we should fail if token-based login fails
        if self._is_running_in_docker():
            print("Running in Docker and token-based login failed. Cannot perform interactive login. Exiting.")
            raise RuntimeError("Cannot perform interactive login in Docker environment.")
        
        # If token-based login fails and we're not in Docker, try interactive login as a last resort
        self.interactive_login()
        print("Successfully logged in to Garmin Connect.")

    def get_activities(self, start: int,limit: int = 1000):
        if self.client is None:
            raise RuntimeError("Not logged in. Please call login() before fetching activities.")
        try:
            activities = self.client.get_activities(start, limit)
            return activities
        except GarminConnectConnectionError:
            print("Connection error occurred while trying to fetch activities from Garmin Connect.")
            raise
        except GarminConnectTooManyRequestsError:
            print("Too many requests. Please wait before trying again.")
            raise

    def download_activity(self, activity_id: str, dl_fmt: Garmin.ActivityDownloadFormat):
        if self.client is None:
            raise RuntimeError("Not logged in. Please call login() before downloading activities.")
        try:
            fit_data = self.client.download_activity(activity_id, dl_fmt)
            return fit_data
        except GarminConnectConnectionError:
            print(f"Connection error occurred while trying to download activity {activity_id}.")
            raise
        except GarminConnectTooManyRequestsError:
            print("Too many requests. Please wait before trying again.")
            raise