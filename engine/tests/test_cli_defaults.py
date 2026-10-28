import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from rec_mlx.cli import main


class DefaultsTests(unittest.TestCase):
    def test_flint_grammar_and_fast_sync_defaults_and_opt_outs(self):
        for options, fast_sync, grammar, enforce, budget in (
            ([], True, "flint", False, None),
            (["--prompts"], True, "flint", False, None),
            (["--no-fast-sync"], False, "flint", False, None),
            (["--grammar", "none"], True, "none", False, None),
            (["--enforce-tool-schemas"], True, "flint", True, None),
            (["--thinking-budget", "0"], True, "flint", False, 0),
            (["--thinking-budget", "512"], True, "flint", False, 512),
        ):
            with self.subTest(options=options):
                engine = Mock(identity={"model_id": "flint"}, startup={"chat_template": "flint"})
                server = Mock(server_port=8080)
                with (
                    patch(
                        "sys.argv",
                        [
                            "rec-mlx",
                            "serve",
                            "flint",
                            "--model-dir",
                            ".",
                            "--manifest",
                            "model.json",
                            *options,
                        ],
                    ),
                    patch.dict(os.environ, {"MLX_METAL_FAST_SYNCH": "0" if fast_sync else "1"}),
                    patch("rec_mlx.cli.Engine", return_value=engine) as construct,
                    patch("rec_mlx.server.make_server", return_value=server) as make,
                    patch("rec_mlx.cli.signal.signal"),
                    redirect_stdout(io.StringIO()) as stdout,
                ):

                    def check_defaults(*args, _fast_sync=fast_sync, _engine=engine, **kwargs):
                        self.assertEqual(
                            os.environ["MLX_METAL_FAST_SYNCH"], "1" if _fast_sync else "0"
                        )
                        self.assertNotIn("chat_template", kwargs)
                        return _engine

                    construct.side_effect = check_defaults
                    main()
                    self.assertEqual(make.call_args.kwargs["prompts"], "--prompts" in options)
                    self.assertEqual(make.call_args.kwargs["grammar_mode"], grammar)
                    self.assertEqual(make.call_args.kwargs["thinking_budget"], budget)
                    self.assertEqual(
                        json.loads(stdout.getvalue().splitlines()[0])["thinking_budget"], budget
                    )
                    self.assertEqual(construct.call_args.kwargs["enforce_tool_schemas"], enforce)
                    ready = json.loads(stdout.getvalue().splitlines()[0])
                    self.assertEqual(ready["grammar"], grammar)
                    self.assertEqual(ready["fast_sync"], fast_sync)
                    self.assertEqual(ready["enforce_tool_schemas"], enforce)
                    self.assertEqual(ready["chat_template"], "flint")

    def test_invalid_thinking_budget_is_rejected_before_loading_weights(self):
        from contextlib import redirect_stderr

        for options in (
            ["--thinking-budget", "-1"],
            ["--thinking-budget", "1", "--grammar", "none"],
        ):
            with (
                self.subTest(options=options),
                patch(
                    "sys.argv",
                    [
                        "rec-mlx",
                        "serve",
                        "flint",
                        "--model-dir",
                        ".",
                        "--manifest",
                        "model.json",
                        *options,
                    ],
                ),
                patch("rec_mlx.cli.Engine") as construct,
                redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
                construct.assert_not_called()
