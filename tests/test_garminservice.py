import pytest
from unittest.mock import MagicMock, patch
from garminservice import GarminService
from garminconnect.exceptions import (
    GarminConnectAuthenticationError, 
    GarminConnectConnectionError, 
    GarminConnectTooManyRequestsError
)

@pytest.fixture
def mock_config():
    """Provides a mock configuration object."""
    config = MagicMock()
    config.user_email = "test@example.com"
    config.user_password = "password123"
    return config

@pytest.fixture
def service(mock_config):
    """Initializes the GarminService with a mock config."""
    return GarminService(mock_config)

def test_is_running_in_docker(service):
    """
    Tests the Docker detection logic by mocking file existence.
    """
    with patch("os.path.exists") as mock_exists:
        # Simulate running inside Docker
        mock_exists.side_effect = lambda p: p == '/.dockerenv'
        assert service._is_running_in_docker() is True
        
        # Simulate running on a host machine
        mock_exists.side_effect = lambda p: False
        assert service._is_running_in_docker() is False

@patch("garminservice.Garmin")
def test_login_with_tokens_success(mock_garmin_class, service):
    """
    Verifies that the service first attempts to log in using 
    stored session tokens.
    """
    mock_client = mock_garmin_class.return_value
    
    # Execution
    service.login()
    
    # Assert that Garmin() was called without arguments (token login)
    mock_garmin_class.assert_any_call()
    mock_client.login.assert_called_once()
    assert service.client is not None

@patch("garminservice.Garmin")
def test_login_fallback_to_credentials(mock_garmin_class, service):
    """
    Tests the fallback mechanism: if token login fails, 
    it should try logging in with email and password.
    """
    # First call (tokens) fails, second call (credentials) succeeds
    mock_garmin_class.side_effect = [
        MagicMock(login=MagicMock(side_effect=GarminConnectAuthenticationError())),
        MagicMock()
    ]
    
    service.login()
    
    # Verify both attempts were made
    assert mock_garmin_class.call_count == 2
    # Verify second attempt used credentials from config
    mock_garmin_class.assert_any_call(
        service.user_email, service.user_password, prompt_mfa=service._get_mfa_code
    )

def test_get_activities_not_logged_in(service):
    """
    Ensures a RuntimeError is raised if fetching activities 
    is attempted without a successful login.
    """
    with pytest.raises(RuntimeError, match="Not logged in"):
        service.get_activities(0, 10)

def test_get_activities_success(service):
    """
    Tests successful activity retrieval by mocking the API client response.
    """
    service.client = MagicMock()
    mock_activities = [{"activityId": "1"}, {"activityId": "2"}]
    service.client.get_activities.return_value = mock_activities
    
    result = service.get_activities(0, 2)
    
    assert result == mock_activities
    service.client.get_activities.assert_called_with(0, 2)

@pytest.mark.parametrize("exception, expected_log", [
    (GarminConnectConnectionError, "Connection error"),
    (GarminConnectTooManyRequestsError, "Too many requests"),
])
def test_get_activities_error_handling(service, exception, expected_log, caplog):
    """
    Checks if API errors during activity retrieval are 
    properly logged and re-raised.
    """
    service.client = MagicMock()
    service.client.get_activities.side_effect = exception
    
    with pytest.raises(exception):
        service.get_activities(0, 10)
    
    assert expected_log in caplog.text

def test_download_activity_success(service):
    """
    Tests successful file download for a specific activity.
    """
    service.client = MagicMock()
    service.client.download_activity.return_value = b"binary_fit_data"
    
    data = service.download_activity("123", "fit")
    
    assert data == b"binary_fit_data"
    service.client.download_activity.assert_called_with("123", "fit")

def test_login_docker_failure(service):
    """
    Verifies that the service fails with a RuntimeError if all login attempts 
    fail while running inside a Docker container.
    """
    # 1. Mock the Docker check to return True
    with patch.object(service, '_is_running_in_docker', return_value=True):
        # 2. Mock the Garmin class
        with patch("garminservice.Garmin") as mock_garmin_class:
            # Create a client mock where login() always fails
            mock_client = MagicMock()
            mock_client.login.side_effect = GarminConnectAuthenticationError()
            mock_garmin_class.return_value = mock_client
            
            # 3. Simulate that credentials are NOT available or failed
            # We set these to None so the code skips the credential login attempt
            # or reaches the end of the login method.
            service.user_email = None
            service.user_password = None

            # Now the code should fail the token login, skip credential login, 
            # and hit the Docker check at the end.
            with pytest.raises(RuntimeError, match="Cannot perform interactive login in Docker environment"):
                service.login()

@patch("garminservice.Garmin")
@patch("garminservice.getpass.getpass")
@patch("garminservice.input")
def test_interactive_login_success(mock_input, mock_getpass, mock_garmin_class, service):
    """
    Tests the interactive login flow by mocking user inputs for 
    email and password and verifying the Garmin client initialization.
    """
    # 1. Setup the mocks for user input
    # mock_input is used for the email
    mock_input.return_value = "user@example.com"
    # mock_getpass is used for the password
    mock_getpass.return_value = "secure_password123"
    
    # 2. Setup the mock for the Garmin client
    mock_client = mock_garmin_class.return_value
    
    # 3. Execute the interactive login
    service.interactive_login()
    
    # 4. Assertions
    # Verify that input() was called to ask for the email
    mock_input.assert_called_with("Enter your Garmin Connect email: ")
    
    # Verify that getpass() was called to ask for the password
    mock_getpass.assert_called_with("Enter your Garmin Connect password: ")
    
    # Verify that the Garmin class was instantiated with the mocked inputs
    # Note: prompt_mfa should be linked to the service's internal method
    mock_garmin_class.assert_called_once_with(
        "user@example.com", 
        "secure_password123", 
        prompt_mfa=service._get_mfa_code
    )
    
    # Verify that the login method was called on the client instance
    mock_client.login.assert_called_once_with(service.token_directory)
    
    # Ensure the client was successfully attached to the service
    assert service.client == mock_client

    @pytest.mark.parametrize("raised_exception, expected_log", [
        # Branch 1: Authentication Error
        (GarminConnectAuthenticationError("Auth Failed"), 
        "Authentication failed. Please check your credentials"),
        
        # Branch 2: Connection Error
        (GarminConnectConnectionError("No Internet"), 
        "Connection error occurred while trying to log in"),
        
        # Branch 3: Generic/Unexpected Error
        (Exception("Unknown Error"), 
        "An unexpected error occurred during login")
    ])
    def test_handle_login_error_branches(service, raised_exception, expected_log, caplog):
        """
        Tests the different branches of _handle_login_error to ensure 
        correct logging and re-raising of exceptions.
        """
        # We call the internal method directly to test the branching logic
        with pytest.raises(type(raised_exception)):
            service._handle_login_error(raised_exception)
        
        # Verify that the correct log message was recorded
        assert expected_log in caplog.text