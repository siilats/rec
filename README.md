<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)"
      srcset=".github/assets/recursive_logo_light.svg">
    <img src=".github/assets/recursive_logo_dark.svg" alt="Recursive"
      width="400">
  </picture>
</p>

`rec` is our custom inference engine for running [Recursive's language
models](https://www.recursive.com/updates/introducing-recursive-flint)
locally on your machine. It provides lightning-fast inference for
single-session usage. Compared to llama.cpp, rec delivers **1.4–2.6×** the
token throughput across the context lengths shown below on M4 Pro. Use it
with pi, OpenCode, or connect your own client through the local API.

<p align="center">
  <img src=".github/assets/throughput.svg"
    alt="Flint decode throughput: rec vs. llama.cpp at context lengths from 1K
    to 252K tokens" width="640">
</p>

<p align="center"><sub>Flint on Apple M4 Pro (48 GB), 4-bit weights,
1K–252K-token prompts and 1,024 output tokens. Five runs per context; prefill
excluded.</sub></p>

## Requirements

- Apple Silicon Mac with an M4 Pro, M4 Max, M5 Pro, or M5 Max
- At least 48 GB unified memory
- About 30 GB free disk space
- [Node.js 22](https://nodejs.org/en/download) and npm for pi


## Install

Install using:

```bash
curl -fsSL https://raw.githubusercontent.com/recursive-oss/rec/main/install.sh | bash
```

This installs `rec` in `~/.local/bin` and adds it to your PATH for new
terminals. All other data lives under `~/.local/share/rec`.


## Usage

We find the best performance from our models when paired with the
[pi](https://pi.dev/) harness. For convenience, rec provides pre-configured
recipes for running pi, omp, and [OpenCode](https://opencode.ai) harnesses. Run
them using:

```bash
rec launch pi  # preferred
rec launch omp
rec launch opencode
```

⚠️ rec is optimized for single-session usage. To run multiple agents at a
time, see our [documentation](https://docs.recursive.com/getting-started) for
other ways to run our models.

This starts our inference server and connects to it automatically. The first
run downloads the model and harness. The model server continues to run after
you close the terminal. Run `rec stop` to stop it.

These harnesses are kept separate from anything on your system. Use
`rec exec pi|omp|opencode ARGS` to run their own commands, for example:

```bash
rec exec pi install npm:PACKAGE
```


### Use your own harness

`rec` exposes OpenAI and Anthropic-compatible chat-completion APIs.
Start the server:

```bash
rec serve
```

Keep this terminal open. When `flint is ready.` appears, connect a client from
another terminal.

For progress during long agent or Harbor runs, opt into content previews:

```bash
rec serve --prompts
```

`--prompts` logs the first 100 Unicode code points of the newest user input or tool result
and the assistant's response to stderr, alongside the existing diagnostics.
Each line includes the same server-generated request ID, including while a
request waits in the queue. Streaming assistant text is printed in fragments
as it arrives, stopping after 100 characters total. The API response and SSE
stream remain complete. Terminal controls and invisible formatting characters
are escaped after truncation; escapes can occupy more than 100 display columns.

For conversations with tools, the prompt preview selects the newest tool result
instead of repeating the original task. Injected `<system-reminder>` blocks are
removed from the preview before truncation; reminder-only messages are skipped.
Text content blocks are joined; images and tool schemas are omitted. These
changes affect diagnostics only: the model still receives the complete prompt.
Assistant text takes precedence over
reasoning and tool calls. If there is no assistant text, a bounded tool-call
name/arguments preview or reasoning preview is labeled `tool-only` or
`reasoning-only` when the request finishes; empty responses are labeled `empty`.

Previews are off by default. Explicitly requested previews can contain private
user content, including secrets pasted into prompts or returned by the model.
The preview logger never reads authentication headers, API keys, or configuration
secrets. Keep this terminal private and take care when redirecting stderr.
Start serving with `--prompts` before attaching a harness; an existing server
with a different preview setting must be stopped first with `rec stop`.

To use your own install of pi or OpenCode, run:

```bash
rec launch --args pi
rec launch --args opencode
```

Each command prints the environment and command line that `rec launch` uses,
instead of running it. Replace the harness path with the path to your own
harness. The command also points the harness at rec's own settings and
sessions; remove those variables to keep yours.

To send a request directly to the OpenAI-compatible API:

```bash
curl -fsS http://127.0.0.1:11500/v1/chat/completions \
  -H "Authorization: Bearer $(rec auth token)" \
  -H 'Content-Type: application/json' \
  -d '{"model":"flint","messages":[{"role":"user","content":"Say hello."}],"max_tokens":128}'
```

The response contains generated text in `choices`. For other clients, use
base URL `http://127.0.0.1:11500/v1`, model `flint`, and the API key from
`rec auth token`.

Set a server-wide default, including for Claude Code's Anthropic API requests:

```sh
rec serve --thinking-budget 512
```

`--thinking-budget 0` suppresses thinking; omit the option for no budget.
Stop an existing server with `rec stop` before changing its budget.
OpenAI chat requests can override this default with their own `thinking_budget`.

To bound the reasoning of a chat request, add `"thinking_budget": N`, a
nonnegative integer. It needs `grammar=flint` (the default). N counts the
tokens after the model's own `<think>`; when N is reached, Flint closes the
`</think>` block itself. A budget of 0 skips reasoning. A prompt that already
ends with `<think>` is rejected with HTTP 400. A prompt with an
unclosed `<think>` anywhere is also rejected. `/v1/messages` rejects only
`thinking_budget` with 400; `thinking.budget_tokens` is ignored as before. When
the request sets `thinking_budget` (0 included), the response `usage` reports
`reasoning_tokens` and `thinking_forced_close`. Streaming responses report them
only in the final usage chunk, so set `stream_options.include_usage`. Without a
request or server-default budget these keys do not appear.

The Anthropic-compatible API is available at
`http://127.0.0.1:11500/v1/messages`. Point `ANTHROPIC_BASE_URL` at
`http://127.0.0.1:11500` and send the token from `rec auth token` as a bearer
token or as `x-api-key`. The model is `flint`.


## Commands

| Command | What it does |
|---|---|
| `rec launch pi\|omp\|opencode` | Start the server if needed and open a harness |
| `rec exec pi\|omp\|opencode ARGS` | Run a harness command, such as installing a plugin |
| `rec serve` | Start the model server in this terminal |
| `rec status` | Show whether the server is running |
| `rec stop` | Stop the server |
| `rec auth token` | Print the local API key |
| `rec pull` | Download the model without starting the server |
| `rec doctor` | Check your hardware and installation |
| `rec update` | Update rec to the latest release |
| `rec uninstall` | Remove rec, its models and its settings |

Run `rec COMMAND --help` for a command's options.


## Help and contributing

- Questions, bugs, and feature requests:
  [GitHub Issues](https://github.com/recursive-oss/rec/issues).
- Contribution guide and local checks: [CONTRIBUTING.md](CONTRIBUTING.md).
- Community guidelines: [Code of conduct](CODE_OF_CONDUCT.md).
- Security vulnerabilities: [Private reporting instructions](SECURITY.md).
- License: [Apache 2.0](LICENSE).
