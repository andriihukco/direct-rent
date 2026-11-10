"""One-off interactive Telethon login. Creates the session file; prints nothing secret."""
from directrent.config import get_settings
from directrent.main import make_telethon


def main() -> None:
    client = make_telethon(get_settings())
    with client:  # prompts for the phone number and the login code on first run
        pass
    print("Session saved")


if __name__ == "__main__":
    main()
