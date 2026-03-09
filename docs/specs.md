Here is the complete Product Requirements Document (PRD) detailing the architecture, business logic, and execution strategy for the AI recruiting system.

# Product Requirements Document (PRD): AI Hiring Box for Delivery Stations

## Project Overview

The "AI Hiring Box" is a hardware-software integrated SaaS solution designed specifically for food delivery station managers (e.g., Meituan). The system operates as an autonomous, 24/7 virtual HR assistant. It uses a combination of Robotic Process Automation (RPA) and Large Language Models (LLMs) to actively source candidates on platforms like Boss Zhipin, conduct initial conversational screening, answer basic job-related questions, and extract candidate contact information (WeChat/Phone numbers) to generate high-quality recruiting leads.

The commercial model relies on a high-margin hardware buyout (a pre-configured mini-PC acting as the "box") coupled with an ongoing subscription/recharge model for AI conversation tokens.

## Core Requirements

* **Anti-Ban Resiliency:** The system must operate locally on a dedicated device (hardware box) using localized IP addresses and human-like interaction pacing to avoid triggering platform anti-bot mechanisms and account bans.
* **Zero-Friction User Experience:** End-users (station managers) lack technical expertise. The final product must be "plug-and-play," requiring only a QR code scan to log in and simple text inputs for configuration.
* **Cost Efficiency:** The underlying LLM must be highly cost-effective to maximize profit margins on token recharges.
* **Non-Intrusive Delivery:** Lead generation notifications must not spam the user. Data should be compiled silently into an easily accessible, centralized location.

## Core Features

* **Automated Target Hunting:** The system actively scrolls through candidate recommendation pages and automatically initiates conversations based on strict hardcoded filters (e.g., "Active Today/Just Now," Job Intent matches "Rider/Courier," Age 18-45).
* **Human-like Screening & Contact Extraction:** AI engages the candidate with an initial screening question (e.g., "Do you have your own e-bike?") to lower defenses, before pivoting to request a phone number or WeChat ID.
* **Station Knowledge Base (RAG):** Managers can input custom station policies (e.g., piece-rate pay, vehicle rental options, accommodation). The AI references this knowledge base to answer complex candidate questions naturally before steering the conversation back to requesting contact info.
* **Automated Lead Harvesting:** The system uses regular expressions (Regex) to instantly detect phone numbers or WeChat IDs in the candidate's replies, tags the candidate as "converted," and stops further AI messaging to prevent robotic looping.

## Core Components

* **The Hardware Node (Execution Engine):** A low-cost, low-spec Windows mini-PC (e.g., Intel N100 processor). Acts as the physical host for the RPA scripts and browser instance.
* **The RPA Controller:** The automation layer responsible for DOM parsing, simulating human mouse movements/clicks, managing browser cookies, and reading/sending messages.
* **The LLM Brain:** The cloud-based AI model that analyzes candidate text, queries the knowledge base, and generates contextual, goal-oriented responses.
* **Data Delivery Pipeline:** A lightweight integration that pushes converted leads directly into an external spreadsheet without requiring a custom frontend dashboard.

## App/User Flow

### Manager (User) Flow

1. **Setup (Demo Phase):** Manager joins a video call, scans a QR code displayed on the developer's screen via the Boss Zhipin mobile app to grant login access.
2. **Configuration:** Manager provides a brief text summary of station benefits, rules, and salary structure (Knowledge Base).
3. **Daily Operation:** Manager checks a designated Feishu/Tencent online spreadsheet at their convenience to view the daily harvested leads (Name, Phone/WeChat, E-bike status) and adds them manually to their contact list.

### System (Bot) Flow

1. **Hunting Loop:**
* Launch browser and inject authentication cookies.
* Navigate to candidate lists.
* Parse UI elements to filter by active status, age, and job intent.
* Simulate human clicks to open profiles and send the initial ice-breaker message.
* Pause/Sleep randomly to mimic human pacing.


2. **Farming Loop:**
* Periodically check the message inbox for unread indicators (red dots).
* Read the candidate's reply.
* Send context + Knowledge Base to the LLM.
* Receive LLM response and type it out into the chat.
* Run Regex scan on the candidate's text. If a number/ID is found -> trigger Webhook to spreadsheet -> tag as "Done" -> exit chat.



## Techstack

* **Primary Language:** Python (for both RPA and backend logic).
* **RPA/Automation:** Playwright (Superior to Selenium for evading anti-bot detection; handles asynchronous tasks efficiently).
* **Backend Framework:** FastAPI (Lightweight, fast, and handles concurrent API calls smoothly).
* **LLM Provider:** DeepSeek API or Qwen (Alibaba) API. (Chosen for exceptional Chinese language comprehension, instruction following, and ultra-low token costs).
* **Data Storage/Sync:** Feishu (Lark) Open API or Tencent Docs Webhook (Direct-to-spreadsheet integration, eliminating the need for a custom database and frontend in the early stages).
* **Hardware (Target Commercial):** Sub-$150 USD Windows Mini PCs (e.g., Intel N100).

## Implementation Plan

### Phase 1: MVP & Core Loop Verification (Weeks 1-2)

* Set up the Playwright environment locally.
* Implement the manual QR code login bypass and cookie extraction.
* Build the *Hunting Loop* (Hardcoded DOM parsing and automated initial messaging).
* *Milestone:* System can successfully log in and send 20 targeted greeting messages without being flagged.

### Phase 2: LLM Integration & Data Extraction (Weeks 3-4)

* Integrate DeepSeek/Qwen API.
* Draft and test the System Prompts for screening and the RAG-based Knowledge Base implementation.
* Implement Regex for phone/WeChat detection.
* Connect the Webhook to push successful extractions to a Feishu/Tencent spreadsheet.
* *Milestone:* System can hold a conversation, answer a basic question, extract a provided number, and populate the spreadsheet.

### Phase 3: Hardware Packaging & Commercialization (Weeks 5+)

* Procure test hardware (Mini PCs).
* Configure Windows environments to auto-run the Python/FastAPI payload on boot.
* Develop a minimal local UI or configuration file system for managers to update their Knowledge Base text easily.
* *Milestone:* First "Smart Hiring Box" is shipped to a pilot station manager for real-world stress testing.