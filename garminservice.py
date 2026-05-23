import os
from garminconnect import Garmin, GarminConnectConnectionError, GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

class GarminService: 

    def __init__(self, user_email: str, user_password: str, token_directory: str = "~/.garmin_tokens"):
        self.user_email = user_email
        self.user_password = user_password
        self.token_directory = os.path.expanduser(token_directory)
        self.client = None

    def login(self):
        try:
            self.client = Garmin()
            self.client.login(self.token_directory)
            print("Logged in using saved tokens.")
            return self.client
        
        except GarminConnectTooManyRequestsError as err:
                print(f"Rate limit: {err}")
                #sys.exit(1)

        except (GarminConnectAuthenticationError, GarminConnectConnectionError):
            print("No valid tokens found — logging in.")

        try:        
            self.client = Garmin(self.user_email, self.user_password)
            self.client.login(self.token_directory)
            print("Successfully logged in to Garmin Connect.")
        except GarminConnectAuthenticationError:
            print("Authentication failed. Please check your email and password.")
            raise
        except GarminConnectConnectionError:
            print("Connection error occurred while trying to connect to Garmin Connect.")
            raise
        except GarminConnectTooManyRequestsError:
            print("Too many requests. Please wait before trying again.")
            raise   

    def get_activities(self, start: int,limit: int = 1000):
        if self.client is None:
            raise Exception("Not logged in. Please call login() before fetching activities.")
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
            raise Exception("Not logged in. Please call login() before downloading activities.")
        try:
            fit_data = self.client.download_activity(activity_id, dl_fmt)
            return fit_data
        except GarminConnectConnectionError:
            print(f"Connection error occurred while trying to download activity {activity_id}.")
            raise
        except GarminConnectTooManyRequestsError:
            print("Too many requests. Please wait before trying again.")
            raise