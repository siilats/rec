"""Opt-in, bounded user-content diagnostics. Never accept headers or configuration."""

import json
import logging
import re
import unicodedata

LIMIT = 100
_REMINDER = re.compile(r"<system-reminder\b[^>]*>.*?</system-reminder\s*>", re.I | re.S)


def prompt_preview(messages):
    """Newest user input or tool result, without injected reminder boilerplate."""
    for message in reversed(messages):
        role = message.get("role")
        if role not in {"user", "tool"}:
            continue
        text = message_text(message.get("content"))
        cleaned, reminders = _REMINDER.subn("", text)
        if reminders:
            cleaned = cleaned.strip()
            if not cleaned:
                continue
        return role, cleaned[:LIMIT]
    return "empty", ""


def terminal_text(text):
    """Quote one line, escaping controls, surrogates and invisible format characters."""
    quoted = json.dumps(text, ensure_ascii=False)
    return "".join(
        f"\\u{ord(char):04x}"
        if unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
        else char
        for char in quoted
    )


def message_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        )
    return ""


class Preview:
    def __init__(self, request_id, messages):
        self.request_id = request_id
        self.thinking = ""
        self.reported = False
        self.finished = False
        role, text = prompt_preview(messages)
        self.emit("prompt " + role, text)

    def emit(self, label, text):
        logging.info("rec_preview [%s] %s: %s", self.request_id, label, terminal_text(text))

    def response(self, message):
        """Observe parsed API messages/deltas without modifying any model/API data."""
        if self.finished or self.reported:
            return
        content = message.get("content")
        if isinstance(content, list):
            text = "".join(
                block.get("thinking", "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "thinking"
                and isinstance(block.get("thinking"), str)
            )
        else:
            # The server observes OpenAI deltas before translating reasoning into
            # Anthropic content[{type: thinking, thinking: ...}] blocks.
            text = message.get("reasoning") or message.get("reasoning_content") or ""
        self.thinking += text[: LIMIT - len(self.thinking)]
        if len(self.thinking) == LIMIT:
            self._report_thinking()

    def _report_thinking(self):
        if self.thinking and not self.reported:
            self.emit("response thinking", self.thinking)
            self.reported = True

    def finish(self):
        self._report_thinking()
        self.finished = True
