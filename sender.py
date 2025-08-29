import time
import random
from playwright.sync_api import sync_playwright, Page, Browser, Playwright, TimeoutError

USER_DATA_DIR = "playwright_user_data"

class WhatsAppSender:
    """
    Manages a persistent browser session to interact with WhatsApp Web.
    """
    p: Playwright = None
    browser: Browser = None
    page: Page = None

    def __init__(self, headless=False):
        self.headless = headless

    def __enter__(self):
        """Starts playwright and launches the browser."""
        self.p = sync_playwright().start()
        self.browser = self.p.chromium.launch(headless=self.headless, user_data_dir=USER_DATA_DIR)
        self.page = self.browser.new_page()
        self._login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Closes the browser and stops playwright."""
        if self.browser:
            self.browser.close()
        if self.p:
            self.p.stop()

    def _login(self):
        """
        Navigates to WhatsApp Web and waits for the user to log in if necessary.
        """
        print("Navigating to WhatsApp Web...")
        self.page.goto("https://web.whatsapp.com", timeout=90000)
        try:
            # Wait for a selector that only appears when logged in
            self.page.wait_for_selector("div[title='New chat']", timeout=15000)
            print("Already logged in.")
        except TimeoutError:
            print("Login required. Please scan the QR code with your phone.")
            print("The script will wait for up to 2 minutes for you to log in.")
            try:
                self.page.wait_for_selector("div[title='New chat']", timeout=120000)
                print("Login successful!")
            except TimeoutError:
                raise Exception("Failed to log in to WhatsApp within the time limit.")

    def read_last_message(self, phone_number: str) -> str | None:
        """
        Reads the very last message from a chat.
        Returns the message text or None if it can't be found.
        """
        try:
            print(f"Opening chat with {phone_number} to read last message...")
            url = f"https://web.whatsapp.com/send?phone={phone_number}"
            self.page.goto(url, timeout=60000)

            # Wait for the main message pane to load
            message_pane_selector = "div[role='application']"
            self.page.wait_for_selector(message_pane_selector, timeout=30000)

            # This selector targets the container for all messages
            # It's a bit generic, but usually stable
            messages_container = self.page.locator("div.x1n2onr6.xy9n6w2")

            # Get the last message element in the container
            last_message = messages_container.locator("div[role='row']").last

            if last_message:
                # The actual text is often in a span inside a div with class '.copyable-text'
                text_element = last_message.locator(".copyable-text")
                if text_element.count() > 0:
                    message_text = text_element.inner_text()
                    print(f"Found last message: '{message_text}'")
                    return message_text.strip()

            print("Could not find any messages in the chat.")
            return None

        except TimeoutError:
            print(f"Timed out while trying to read messages for {phone_number}.")
            return None
        except Exception as e:
            print(f"An error occurred while reading messages for {phone_number}: {e}")
            return None

    def send_message(self, phone_number: str, message: str) -> str:
        """
        Sends a message to a given phone number. Assumes the page is already open.
        """
        try:
            print(f"Preparing to send message to {phone_number}...")
            url = f"https://web.whatsapp.com/send?phone={phone_number}"
            self.page.goto(url, timeout=60000)

            message_box_selector = 'div[title="Type a message"]'
            self.page.wait_for_selector(message_box_selector, timeout=60000)

            self.page.fill(message_box_selector, message)
            time.sleep(random.uniform(1, 3))

            send_button_selector = 'button[aria-label="Send"]'
            self.page.click(send_button_selector)
            time.sleep(random.uniform(2, 4))

            print(f"Successfully sent message to {phone_number}")
            return "Success"

        except TimeoutError:
            print(f"Error: Timed out while trying to send message to {phone_number}.")
            return "Fail: Timeout"
        except Exception as e:
            print(f"An unexpected error occurred during sending: {e}")
            return f"Fail: {e}"

# Example of how this class would be used
if __name__ == '__main__':
    test_phone_number = "12025550192" # Replace with a real number for testing
    test_message = "Hello from the new Manzam sender! This is a test."

    with WhatsAppSender(headless=False) as sender:
        # Test reading a message
        last_msg = sender.read_last_message(test_phone_number)
        print(f"\n--- Reading Test ---")
        if last_msg:
            print(f"The last message was: '{last_msg}'")
        else:
            print("Could not read the last message.")

        # Test sending a message
        print(f"\n--- Sending Test ---")
        result = sender.send_message(test_phone_number, test_message)
        print(f"Send result: {result}")

    print("\nScript finished.")
