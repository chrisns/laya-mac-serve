# Laya Serve for macOS

A macOS menu bar application that serves [Laya](https://github.com/NandhaKishorM/laya)
over HTTP with an OpenAI-compatible interface. Point the n8n **Text Classifier** node at
it and classify emails on your own Mac.

Laya is a non-autoregressive decision engine from Convai Innovations. It answers typed
questions in one forward pass of about 40 ms. It does not generate text, so it cannot
hallucinate an answer that is outside your category list.

The weights ship inside the application. It needs no network, no Hugging Face account
and no download at run time.

## What it does

- Runs a local HTTP server that speaks the OpenAI chat completions protocol.
- Translates each n8n classification request into Laya typed questions.
- Returns the exact JSON object that the n8n node expects.
- Holds the model weights inside the application, so it works with no network.
- Unloads the model after an idle period, and loads it again on the next request.
- Lives in the menu bar. It has no Dock icon and no window.

## Requirements

- Apple Silicon. PyTorch has no current macOS x86_64 wheel.
- macOS 13 or later.
- About 1.5 GB of disk. That holds CPython, PyTorch and the weights.
- About 1.3 GB of memory while the model is loaded, and about 60 MB when it is not.

## Install

1. Download the disk image from the
   [latest release](https://github.com/chrisns/laya-mac-serve/releases/latest).
2. Drag `LayaServe.app` to Applications.
3. The application is signed ad-hoc, not notarised. Remove the quarantine flag:

   ```bash
   xattr -dr com.apple.quarantine /Applications/LayaServe.app
   ```

4. Start the application. A brain icon appears in the menu bar.

The first classification loads the model, which takes about 30 seconds. Later requests
take about 40 ms. Use **Load model now** in the menu to load it before the first
workflow runs.

## The menu

| Item | What it does |
|---|---|
| Status line | Shows the loaded model, the device and the memory use. |
| Copy base URL | Copies the URL for the n8n credential. |
| Load model now | Loads the model, so the first classification is fast. |
| Unload model now | Frees the memory at once. |
| Unload when idle for | Never, 5 minutes, 15 minutes, 30 minutes, 1 hour, 2 hours, 4 hours. |
| Default model | The checkpoint to use when the request names none. A checkpoint that is not in the application shows "(downloads)". |
| Allow connections from the network | Binds to all interfaces and generates an API key. |
| Open log file | Opens `~/Library/Logs/LayaServe/server.log`. |
| Open settings folder | Opens the folder that holds `config.json`. |
| Quit Laya Serve | Stops the server and quits. |

## Set up n8n

Warning: the server listens on `127.0.0.1` at first. Your n8n cluster cannot reach it
until you turn on **Allow connections from the network**. That menu item generates an
API key. Keep the key secret.

1. In n8n, create an **OpenAI** credential.
2. Set the **Base URL** to `http://<your-mac>:5292/v1`.
3. Set the **API Key** to the key from the menu. Use any non-empty text when you run
   n8n on the same Mac and you did not set a key.
4. Add an **OpenAI Chat Model** sub-node. Pick `laya-typed-decisions` from the model
   list.
5. Connect it to a **Text Classifier** node. Add your categories and descriptions.

Give every category a clear description. Laya reads the description, not the category
name alone.

Keep the category list short. Laya gives 192 tokens to all the options together, so
twenty categories with long descriptions lose detail. The server cuts each description
to 240 characters for the same reason.

### Node support

| n8n node | Works | Why |
|---|---|---|
| Text Classifier | Yes | This is the target use. Single label and multiple labels both work. |
| Sentiment Analysis | Yes | The schema is a string enum, which maps to a Laya `choice` question. |
| Information Extractor | No | It asks the model to write field values. Laya cannot generate text. |
| Basic LLM Chain | No | It asks for free text. |

A request that asks for free text returns HTTP 400 with a clear message. It does not
return a made-up answer.

## How the translation works

The n8n Text Classifier sends a system message that holds a JSON Schema, and a user
message that holds the text. Each category is a boolean property. The node parses the
reply with the LangChain `StructuredOutputParser`.

Laya Serve reads the JSON Schema out of the prompt and builds Laya questions from it.

- **One label at a time.** One `choice` question. The criteria are your categories and
  their descriptions. The winner becomes `true`.
- **Several labels at a time.** One `noul` question for each category. A probability at
  or above `multi_label_threshold` becomes `true`.
- **The fallback category.** Laya gets an extra `other` option. The `fallback` property
  is also set when the winning probability is under `fallback_probability_floor`.

Every reply carries an `x_laya` object with the probabilities and the confidence. The
n8n node ignores it. It is there for debugging.

## Endpoints

| Route | Purpose |
|---|---|
| `GET /health` | Liveness. It never loads the model. |
| `GET /status` | The model state, the device and the memory use. |
| `GET /v1/models` | Lists the four model identities. |
| `POST /v1/chat/completions` | The OpenAI interface. It supports `stream: true`. |
| `POST /v1/classify` | Native Laya typed questions. |
| `POST /admin/load` | Loads the model now. |
| `POST /admin/unload` | Unloads the model now. |
| `GET /admin/config`, `POST /admin/config` | Reads and writes the settings. |

### The native endpoint

Use `POST /v1/classify` from the n8n **HTTP Request** node when you want scores and
probabilities rather than booleans.

```bash
curl -s http://127.0.0.1:5292/v1/classify -H 'Content-Type: application/json' -d '{
  "model": "laya-typed-decisions",
  "state": {
    "from": "user@acme.com",
    "subject": "Duplicate charge on invoice #4411",
    "body": "We were billed twice for March. Please refund the duplicate today."
  },
  "questions": {
    "department": {
      "type": "choice",
      "instructions": "Which department should handle this request?",
      "criteria": {
        "billing": "invoices, payments, refunds",
        "technical": "bugs, outages, system errors",
        "sales": "pricing, new contracts"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "How urgent is this request?",
      "criteria": ["not urgent", "soon", "critical"]
    },
    "churn_risk": {
      "type": "noul",
      "instructions": "Does the writer threaten to cancel?"
    }
  }
}'
```

## The models

| Model identity | Checkpoint | Parameters | Context | In the application |
|---|---|---|---|---|
| `laya-typed-decisions` | fine-tuned ModernBERT-large | 421M | 1024 | Yes. This is the default. |
| `laya` | ModernBERT-large | 421M | 512 | No. It downloads on first use. |
| `laya-multilingual` | mmBERT-base | 322M | 1024 | No. It downloads on first use. |
| `laya-router` | all of them | - | - | No. It downloads on first use. |

Only the default checkpoint ships inside the application. Three checkpoints would make
the disk image too large. The model card reports 0.766 accuracy for the fine-tuned
typed-decisions checkpoint against 0.362 for a base checkpoint with no fine-tuning, so
the default is the right one for email triage.

Warning: the other three identities need a download from Hugging Face on first use.
Pick one of them only if you classify text that is not English. `GET /v1/models`
reports `x_bundled` for each identity, and the menu marks them.

## Settings

The settings live in `~/Library/Application Support/LayaServe/config.json`. The menu bar
application and the server share the file. Environment variables override it.

| Key | Default | Purpose |
|---|---|---|
| `host` | `127.0.0.1` | Set to `0.0.0.0` to reach the server from your n8n cluster. |
| `port` | `5292` | The listening port. |
| `api_key` | `null` | When set, every `/v1` request needs `Authorization: Bearer <key>`. |
| `default_model` | `laya-typed-decisions` | The model to use when the request names none. |
| `idle_unload_seconds` | `900` | `0` never unloads. |
| `device` | `auto` | `auto` uses the Apple GPU through MPS, and falls back to the CPU. |
| `multi_label_threshold` | `0.5` | The cut-off for a multiple label classification. |
| `fallback_probability_floor` | `0.35` | Under this winning probability, the fallback category wins. |
| `hf_token` | `null` | A Hugging Face token, for a higher download rate limit. |

A change of `host`, `port` or `api_key` restarts the server. Other changes take effect
at once.

There is no settings key for the model folder. Set the environment variable
`LAYA_SERVE_MODEL_DIR` to point the server at your own checkpoint folder. That folder
holds one directory for each checkpoint: `typed-decisions`, `english` or
`multilingual`.

## Measured performance

On an M1 Max with `laya-typed-decisions` on MPS:

| Step | Measurement |
|---|---|
| First classification, including the model load | about 34 seconds |
| Each classification after that | about 40 ms |
| Resident memory while loaded | about 1.3 GB |
| Resident memory after the idle unload | about 60 MB |
| Application on disk | about 1.5 GB |

## Build it yourself

```bash
git clone https://github.com/chrisns/laya-mac-serve.git
cd laya-mac-serve

# The Python server on its own
python3 -m venv .venv && .venv/bin/pip install -r server/requirements-runtime.txt
PYTHONPATH=server .venv/bin/python -m laya_serve

# The full application
./scripts/build_runtime.sh   # downloads CPython and PyTorch, about 5 minutes
./scripts/fetch_model.sh     # downloads the weights, about 810 MB
./scripts/build_app.sh       # assembles and signs build/LayaServe.app
./scripts/package.sh         # makes the zip and the disk image
```

Run the tests:

```bash
cd server && LAYA_SERVE_FAKE_MODEL=1 pytest -q   # the server
swift test --package-path app                    # the menu bar application
./scripts/smoke_test.sh                          # an end-to-end check with a stub model
./scripts/offline_test.sh                        # an end-to-end check with the real
                                                 # weights and no network access
```

Set `LAYA_SERVE_FAKE_MODEL=1` to replace the model with a deterministic stub. CI uses
it, so CI needs neither PyTorch nor the weights.

## Licence

MIT. See [LICENSE](LICENSE).

The Laya model and the `laya` Python package are Apache 2.0, by
[Convai Innovations](https://huggingface.co/convaiinnovations/laya). The application
ships those weights under that licence. This project is not affiliated with Convai
Innovations or with n8n.
