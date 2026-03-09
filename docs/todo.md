Here is the detailed, step-by-step implementation plan based on the PRD. It is structured to ensure a smooth progression from environment setup to the final hardware-ready deployment, with no sudden jumps in complexity.

### Phase 1: Foundation & Authentication Setup

This phase focuses on setting up the local environment and ensuring we can reliably log into the target platform (Boss Zhipin) without triggering immediate anti-bot defenses.

* [x] **Task ID: 1 - Project Initialization & Environment Setup**
* **Context:** Set up the Python environment and install core dependencies. We need FastApi for any local API routing (future-proofing for local UI) and Playwright for automation.
* **Dependencies:** None
* **Subtasks:**
* [x] Initialize a new Python virtual environment (`python -m venv venv`).
* [x] Create a `requirements.txt` file including `playwright`, `fastapi`, `uvicorn`, `requests`, `python-dotenv`, and `openai` (for DeepSeek/Qwen API compatibility).
* [x] Install dependencies and run `playwright install chromium` to download the browser binaries.
* [x] Create the base project folder structure (`/config`, `/core`, `/logs`, `/utils`).




* [x] **Task ID: 2 - Playwright Stealth Configuration**
* **Context:** Standard Playwright scripts are easily detected. We must configure the browser context to spoof a regular user agent, mask the `webdriver` flag, and randomize viewport sizes.
* **Dependencies:** [1]
* **Subtasks:**
* [x] Create a `browser_manager.py` file.
* [x] Implement a function to launch a persistent Chromium context (`playwright.chromium.launch_persistent_context`).
* [x] Add stealth arguments (e.g., `--disable-blink-features=AutomationControlled`, custom User-Agent string).
* [x] Implement a helper function for randomized human-like delays (e.g., `random_sleep(min_sec, max_sec)`).




* [x] **Task ID: 3 - Manual QR Login & Cookie Management**
* **Context:** To bypass complex CAPTCHAs, we will use a "Video Call/Screen Share" login method for the MVP. The script must pause, wait for the manager to scan the QR code, and then save the session state (cookies) to disk for future re-runs.
* **Dependencies:** [2]
* **Subtasks:**
* [x] Write a script to navigate to the Boss Zhipin login page.
* [x] Implement a polling loop that checks for a successful login DOM element (e.g., the user avatar or dashboard container).
* [x] Upon detecting a successful login, use Playwright's `context.storage_state(path="state.json")` to save the authentication cookies.
* [x] Update `browser_manager.py` to check for `state.json` on startup and inject it to bypass the login screen on subsequent runs.





### Phase 2: The "Hunting Loop" (Automated Sourcing)

This phase implements the active outreach component. The bot will parse the recommendation feed and send ice-breakers based on strict criteria.

* [x] **Task ID: 4 - Candidate Feed Navigation & Pagination**
* **Context:** The bot needs to reach the "Recommend" page and be able to scroll to load new candidate cards.
* **Dependencies:** [3]
* **Subtasks:**
* [x] Create `hunter.py`.
* [x] Implement navigation to the specific candidate recommendation URL.
* [x] Implement a smooth, randomized scrolling function that scrolls down the page in increments, pausing occasionally to trigger dynamic loading (AJAX).




* [x] **Task ID: 5 - DOM Parsing & Filtering Logic**
* **Context:** We must extract data from the HTML structure of the candidate cards and apply our hardcoded filtering rules (Age 18-45, specific job intent, active status).
* **Dependencies:** [4]
* **Subtasks:**
* [x] Write Playwright selectors to target candidate cards.
* [x] Extract text content for "Active Status" (e.g., "刚刚活跃"), "Expected Job" (e.g., "外卖骑手"), and "Age".
* [x] Write a Python filtering function that returns `True` only if the candidate matches the PRD requirements.




* [x] **Task ID: 6 - Interaction Execution (The "Greeting")**
* **Context:** Once a candidate passes the filter, the bot must click the "Chat/Greet" button and verify the message was sent.
* **Dependencies:** [5]
* **Subtasks:**
* [x] Implement the simulated mouse click on the "Greet" button for the approved candidate card.
* [x] Handle the pop-up chat window (if applicable) or verify the UI changes to "Message Sent".
* [x] Write the candidate's ID or URL to a local SQLite DB or JSON file (`contacted_list.json`) to prevent messaging the same person twice.





### Phase 3: The "Farming Loop" (Message Reception & LLM)

This phase handles reading replies from candidates, formatting the context, and generating an AI response.

* [x] **Task ID: 7 - Inbox Navigation & Unread Detection**
* **Context:** The bot must periodically switch from hunting to checking the message inbox for replies.
* **Dependencies:** [3]
* **Subtasks:**
* [x] Create `farmer.py`.
* [x] Implement navigation to the Chat/Message list page.
* [x] Write a DOM selector to identify chat threads with a "red dot" or "unread" class.
* [x] Implement logic to click into the topmost unread chat thread.




* [x] **Task ID: 8 - Chat Context Extraction**
* **Context:** To provide the LLM with enough information, we need to scrape the last 3-5 messages in the current chat window.
* **Dependencies:** [7]
* **Subtasks:**
* [x] Write Playwright locators to target the message bubbles inside the active chat window.
* [x] Extract the text and categorize them by sender (e.g., "Me:", "Candidate:").
* [x] Format the extracted messages into a structured list of dictionaries (OpenAI message format: `[{"role": "user", "content": "..."}, ...]`).




* [x] **Task ID: 9 - LLM Integration & Prompt Engineering**
* **Context:** Connect to the DeepSeek or Qwen API, provide it with the extracted chat history, and define its persona (Station Manager).
* **Dependencies:** [8]
* **Subtasks:**
* [x] Create `llm_service.py`. Initialize the API client using the `openai` Python package pointing to the DeepSeek/Qwen base URL.
* [x] Draft the `System Prompt` detailing the persona, the goal (get WeChat/Phone), and the strict instruction to keep replies short and human-like.
* [x] Create a function `generate_reply(chat_history)` that calls the API and returns the string response.




* [x] **Task ID: 10 - AI Response Typing & Sending**
* **Context:** Take the LLM's response and inject it back into the Boss Zhipin chat window.
* **Dependencies:** [9]
* **Subtasks:**
* [x] In `farmer.py`, implement a locator for the chat input text box.
* [x] Use `page.type(selector, text, delay=100)` to simulate human typing speed (do NOT use instant `page.fill()`).
* [x] Implement the click on the "Send" button or simulate pressing the "Enter" key.





### Phase 4: Data Harvesting & RAG Refinement

This phase finalizes the business value: extracting the lead and answering complex questions using the Knowledge Base.

* [x] **Task ID: 11 - Knowledge Base (RAG) Implementation**
* **Context:** Load station-specific rules from a local file so the LLM can answer questions accurately without hallucinating.
* **Dependencies:** [9]
* **Subtasks:**
* [x] Create a `station_kb.txt` file containing dummy station rules (pay rate, accommodation, etc.).
* [x] Modify `llm_service.py` to read this file on startup.
* [x] Append the contents of `station_kb.txt` to the `System Prompt` context block so the LLM is aware of the rules during every API call.




* [x] **Task ID: 12 - Lead Detection via Regex**
* **Context:** We must scan every incoming message from the candidate to see if they provided their contact info.
* **Dependencies:** [8]
* **Subtasks:**
* [x] Create `extractor.py`.
* [x] Write a Regex pattern to match 11-digit Chinese phone numbers (e.g., `^1[3-9]\d{9}$`).
* [x] Write a Regex pattern to match common WeChat ID formats (alphanumeric, 6-20 characters, often preceded by "wx", "微信", etc.).
* [x] Create a function `check_for_lead(candidate_message)` that returns the extracted number/ID or `None`.




* [x] **Task ID: 13 - Webhook Delivery & Chat Closure**
* **Context:** Once a lead is found, push it to an external spreadsheet and stop the AI from replying further.
* **Dependencies:** [12]
* **Subtasks:**
* [x] Create a free Feishu/Tencent Docs webhook URL (or use a simple mock HTTP POST endpoint for local testing).
* [x] Write a function in `extractor.py` that sends a POST request with the candidate's Name and Contact Info to the webhook.
* [x] Update the local `contacted_list.json` (from Task 6) to mark this candidate's ID as `status: converted`. Update `farmer.py` to skip unread messages from "converted" candidates.





### Phase 5: Orchestration & Hardware Packaging

This final phase ties the hunting and farming loops together into a continuous, 24/7 autonomous script suitable for the "Hiring Box".

* [x] **Task ID: 14 - Master Event Loop (The Orchestrator)**
* **Context:** The system needs a main controller to switch between hunting for new candidates and replying to existing messages.
* **Dependencies:** [6, 10, 13]
* **Subtasks:**
* [x] Create `main.py`.
* [x] Implement a `while True:` loop.
* [x] Define the logic: Run `hunter.py` for 10 minutes (or 20 greetings) -> switch to `farmer.py` for 5 minutes (process all unread messages) -> repeat.
* [x] Implement global error handling (`try/except`) to catch Playwright timeouts or network drops, ensuring the script restarts the browser rather than crashing completely.




* [x] **Task ID: 15 - Windows Deployment Packaging**
* **Context:** Prepare the application to run automatically on the target hardware (Windows Mini-PC) without user intervention.
* **Dependencies:** [14]
* **Subtasks:**
* [x] Create a simple `.bat` script that activates the Python virtual environment and runs `main.py`.
* [x] Document the steps to add this `.bat` file to the Windows Startup folder (shell:startup).
* [x] (Optional) Configure a basic logging rotation (`logging` module) to ensure the local hard drive doesn't fill up with log files over months of operation.