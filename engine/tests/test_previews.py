"""Terminal previews are bounded observations, never transformations of API output."""

import http.client
import io
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from unittest.mock import patch

import pytest

from rec_mlx.previews import Preview, terminal_text
from test_thinking_budget_server import ServerCase


def previews(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("rec_preview")]


@pytest.mark.parametrize("text", ["", "Hi", "😀界é" * 80, "x" * 100, "x" * 101])
def test_prompt_and_response_limits(caplog, text):
    caplog.set_level(logging.INFO)
    preview = Preview("request-one", [{"role": "user", "content": text}])
    preview.response({"content": text})
    preview.finish()
    rows = previews(caplog)
    assert len(rows) == 2
    assert rows[0].endswith(terminal_text(text[:100]))
    assert rows[1].endswith(terminal_text(text[:100]))
    assert all("[request-one]" in row for row in rows)


def test_streaming_is_immediate_and_shares_a_unicode_limit(caplog):
    caplog.set_level(logging.INFO)
    preview = Preview("stream", [{"role": "user", "content": "go"}])
    preview.response({"reasoning": "hidden thought"})
    assert len(previews(caplog)) == 1
    preview.response({"content": "😀" * 60})
    assert previews(caplog)[-1].endswith(terminal_text("😀" * 60))
    preview.response({"content": "界" * 70})
    assert previews(caplog)[-1].endswith(terminal_text("界" * 40))
    preview.response({"content": "MUST NOT APPEAR"})
    preview.finish()
    assert len(previews(caplog)) == 3


def test_latest_input_in_multimessage_and_tool_conversation(caplog):
    caplog.set_level(logging.INFO)
    Preview(
        "multi",
        [
            {"role": "system", "content": "system secret"},
            {"role": "user", "content": "old question"},
            {"role": "assistant", "content": "old answer"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "latest "},
                    {"type": "image_url", "image_url": {"url": "private url"}},
                    {"type": "text", "text": "question"},
                ],
            },
            {"role": "assistant", "tool_calls": [{"function": {"name": "lookup"}}]},
            {"role": "tool", "content": "new tool result"},
        ],
    )
    assert previews(caplog) == ['rec_preview [multi] prompt tool: "new tool result"']
    Preview(
        "empty-user", [{"role": "user", "content": ""}, {"role": "tool", "content": "fresh result"}]
    )
    assert previews(caplog)[-1].endswith('prompt tool: "fresh result"')
    Preview("tool", [{"role": "tool", "content": "result"}])
    assert previews(caplog)[-1].endswith('prompt tool: "result"')
    Preview("empty", [])
    assert previews(caplog)[-1].endswith('prompt empty: ""')


@pytest.mark.parametrize(
    "message,label,text",
    [
        ({"reasoning": "think"}, "reasoning-only", "think"),
        (
            {"tool_calls": [{"function": {"name": "lookup", "arguments": '{"q":1}'}}]},
            "tool-only",
            'lookup{"q":1}',
        ),
        ({}, "empty", ""),
    ],
)
def test_fallback_labels(caplog, message, label, text):
    caplog.set_level(logging.INFO)
    preview = Preview("fallback", [])
    preview.response(message)
    preview.finish()
    preview.finish()
    assert len(previews(caplog)) == 2
    assert previews(caplog)[-1].endswith(f"response {label}: {terminal_text(text)}")


def test_controls_are_escaped_after_counting_source_characters(caplog):
    caplog.set_level(logging.INFO)
    text = "\x1b[31m\r\n\t\x00\x7f\x85\u202e\u2028\ud800" + "界" * 150
    preview = Preview("safe", [{"role": "user", "content": text}])
    preview.response({"content": text})
    preview.finish()
    for row in previews(caplog):
        assert row.endswith(terminal_text(text[:100]))
        assert all(c not in row for c in "\x1b\r\n\t\x00\x7f\x85\u202e\u2028\ud800")
        assert "\\u001b" in terminal_text("\x1b")


class PreviewHTTPTests(ServerCase):
    server_options = {"prompts": True, "api_key": "configuration-secret"}

    def post(self, path, body):
        # Authenticated HTTP requests ensure headers are never among the preview fields.
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            conn.request(
                "POST",
                path,
                json.dumps(body),
                {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer configuration-secret",
                },
            )
            response = conn.getresponse()
            return response.status, response.read().decode()
        finally:
            conn.close()

    def test_stream_and_nonstream_payloads_are_complete(self):
        self.engine.context_limit = 512
        for stream in (False, True):
            with self.subTest(stream=stream), self.assertLogs(level="INFO") as logs:
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    status, body = self.chat(max_tokens=150, stream=stream)
                self.assertEqual(status, 200, body)
                self.assertEqual(stdout.getvalue(), "")
            rows = [
                r.getMessage() for r in logs.records if r.getMessage().startswith("rec_preview")
            ]
            request_id = rows[0].split("[")[1].split("]")[0]
            self.assertTrue(all(f"[{request_id}]" in row for row in rows))
            self.assertNotIn("configuration-secret", "\n".join(rows))
            fragments = [
                json.loads(row.split("response assistant: ")[1])
                for row in rows
                if "response assistant:" in row
            ]
            self.assertEqual("".join(fragments), "x" * 100)
            if stream:
                chunks = [
                    json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: {")
                ]
                text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
                self.assertIn("data: [DONE]", body)
            else:
                text = json.loads(body)["choices"][0]["message"]["content"]
            self.assertEqual(text, "x" * 150)

    def test_anthropic_previews_and_payload(self):
        with self.assertLogs(level="INFO") as logs:
            status, body = self.post(
                "/v1/messages",
                {
                    "model": "flint",
                    "max_tokens": 2,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": "BB"}]}],
                },
            )
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["content"][0]["text"], "xx")
        self.assertTrue(any('prompt user: "BB"' in row for row in logs.output))
        self.assertTrue(any('response assistant: "xx"' in row for row in logs.output))

    def test_queued_tool_conversation_has_distinct_association(self):
        started = threading.Event()
        proceed = threading.Event()
        original = self.engine.generate_tokens

        def paused(ids, *args, **kwargs):
            if ids[0] == ord("A"):
                started.set()
                assert proceed.wait(3)
            yield from original(ids, *args, **kwargs)

        messages = [
            {"role": "system", "content": "system-private"},
            {"role": "user", "content": "old-private"},
            {"role": "assistant", "content": "answer-private"},
            {"role": "user", "content": "latest-question"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "BB"},
        ]
        with patch.object(self.engine, "generate_tokens", side_effect=paused):
            with self.assertLogs(level="INFO") as logs, ThreadPoolExecutor() as pool:
                first = pool.submit(
                    self.chat, max_tokens=2, messages=[{"role": "user", "content": "A"}]
                )
                try:
                    self.assertTrue(started.wait(2))
                    second = pool.submit(self.chat, max_tokens=2, messages=messages)
                    deadline = time.monotonic() + 2
                    while self.server.generator.requests.qsize() < 1:
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.01)
                    rows = [r.getMessage() for r in logs.records if "rec_preview" in r.getMessage()]
                    self.assertEqual(len(rows), 2)
                    self.assertTrue(rows[0].endswith('prompt user: "A"'))
                    self.assertTrue(rows[1].endswith('prompt tool: "BB"'))
                    self.assertNotEqual(rows[0].split("]")[0], rows[1].split("]")[0])
                finally:
                    proceed.set()
                self.assertEqual(first.result()[0], 200)
                self.assertEqual(second.result()[0], 200)
                rows = [r.getMessage() for r in logs.records if "rec_preview" in r.getMessage()]
                self.assertEqual(len(rows), 4)
                for prompt in rows[:2]:
                    matching = [
                        row for row in rows[2:] if row.split("]")[0] == prompt.split("]")[0]
                    ]
                    self.assertEqual(len(matching), 1)
                    self.assertTrue(matching[0].endswith('response assistant: "xx"'))
                self.assertNotIn("private", "\n".join(rows))

    def test_preview_arrives_before_stream_finishes(self):
        # Pause the decoder after an early chunk; no final response exists at this point.
        original = self.engine.generate_tokens
        first = threading.Event()
        proceed = threading.Event()

        def paused(*args, **kwargs):
            for i, event in enumerate(original(*args, **kwargs)):
                yield event
                if i == 15:
                    first.set()
                    assert proceed.wait(3)

        with patch.object(self.engine, "generate_tokens", side_effect=paused):
            with self.assertLogs(level="INFO") as logs, ThreadPoolExecutor() as pool:
                result = pool.submit(self.chat, max_tokens=28, stream=True)
                try:
                    self.assertTrue(first.wait(3))
                    # The HTTP consumer and decoder run on separate threads.
                    deadline = time.monotonic() + 2
                    while not any("response assistant:" in row for row in logs.output):
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.01)
                    self.assertFalse(result.done())
                finally:
                    proceed.set()
                self.assertEqual(result.result()[0], 200)


class DisabledPreviewHTTPTests(ServerCase):
    def test_default_mode_never_constructs_a_preview(self):
        with patch("rec_mlx.previews.Preview") as preview:
            for stream in (False, True):
                self.assertEqual(self.chat(max_tokens=2, stream=stream)[0], 200)
        preview.assert_not_called()


def test_new_user_information_skips_repeated_system_reminders(caplog):
    caplog.set_level(logging.INFO)
    content = (
        "<system-reminder>Attribution for git commits "
        + "x" * 200
        + "</system-reminder>\n\nInspect solve.py and fix the contact constraints."
    )
    messages = [{"role": "user", "content": content}]
    Preview("new-info", messages)
    assert previews(caplog) == [
        'rec_preview [new-info] prompt user: "Inspect solve.py and fix the contact constraints."'
    ]
    assert messages[0]["content"] == content


def test_new_tool_result_takes_precedence_over_old_user_request(caplog):
    caplog.set_level(logging.INFO)
    Preview(
        "tool-update",
        [
            {"role": "user", "content": "old task"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": "Bash", "arguments": "{}"}}],
            },
            {
                "role": "tool",
                "content": "<system-reminder>repeated instructions</system-reminder>\n"
                + "new test failure " * 20,
            },
        ],
    )
    assert previews(caplog) == [
        "rec_preview [tool-update] prompt tool: " + terminal_text(("new test failure " * 20)[:100])
    ]


def test_reminder_only_message_does_not_hide_latest_tool_result(caplog):
    caplog.set_level(logging.INFO)
    Preview(
        "reminder-only",
        [
            {"role": "tool", "content": "fresh output"},
            {
                "role": "user",
                "content": "<system-reminder>Attribution boilerplate</system-reminder>",
            },
        ],
    )
    assert previews(caplog) == ['rec_preview [reminder-only] prompt tool: "fresh output"']


def test_structured_content_skips_multiple_reminders(caplog):
    caplog.set_level(logging.INFO)
    Preview(
        "blocks",
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<system-reminder>first</system-reminder>\n"},
                    {
                        "type": "text",
                        "text": "<system-reminder>second</system-reminder>\nInspect the new failure.",
                    },
                ],
            }
        ],
    )
    assert previews(caplog) == ['rec_preview [blocks] prompt user: "Inspect the new failure."']
