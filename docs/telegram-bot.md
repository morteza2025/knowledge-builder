# Telegram Local Bot API interface

## Architecture

Telegram is an interface adapter under `app/interfaces/telegram`. It validates
and copies a document into a controlled input directory, then constructs the
existing `ProcessingContext` and executes the shared `ProcessBookUseCase`.
Handlers never import pdfplumber, pytesseract, or exporter implementations.

The flow is:

`Telegram update → access control → atomic ingestion → SQLite job queue → ProcessBookUseCase → existing exporters → Telegram delivery`

The bot uses long polling only. No webhook is installed.

## Direct and forwarded documents

Any received message containing a Telegram `document` is handled identically,
whether uploaded directly or forwarded from a private chat, group, or channel.
Forward metadata is recorded only as `source_type`; acceptance never depends on
the original chat being visible.

The adapter checks extension, MIME metadata when present, configured size,
sanitized filename, disk capacity, regular-file/symlink safety, and the `%PDF-`
header. Local Bot API absolute paths are copied into the controlled input
directory; relative paths use a chunked HTTP fallback. A `.part` file is
validated before atomic rename.

## Why a Local Bot API Server is required

The public Bot API download path is unsuitable for the expected 200–300 MB
books. The official Local Bot API server in `--local` mode removes download
limits, supports uploads up to 2000 MB, and returns absolute paths from
`getFile`. It requires a Telegram `api_id` and `api_hash` in addition to the bot
token. Bind port 8081 to localhost unless the Python bot runs on the same
private container network.

python-telegram-bot 22.x expects base URLs that end in `/bot` and `/file/bot`;
the library appends the bot token. `local_mode=True` enables local-path uploads.

## BotFather and API credentials

1. Create or select the bot through BotFather and obtain its token.
2. Obtain `api_id` and `api_hash` from <https://my.telegram.org>.
3. Store secrets in a root-readable environment file outside the repository,
   for example `/etc/knowledge-builder/telegram.env` with mode `0600`.
4. Set `TELEGRAM_ALLOWED_USER_IDS` to a comma-separated allowlist.

Never put real credentials in source files, Compose files, unit files, test
fixtures, command-line arguments, or documentation.

## Environment variables

The complete placeholders live in `.env.example`. Essential values:

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_BOT_API_BASE_URL=http://127.0.0.1:8081/bot
TELEGRAM_BOT_API_FILE_URL=http://127.0.0.1:8081/file/bot
TELEGRAM_ALLOWED_USER_IDS=
TELEGRAM_PROCESSING_CONCURRENCY=1
TELEGRAM_JOB_QUEUE_SIZE=10
TELEGRAM_MAX_FILE_SIZE_MB=1900
```

An empty or malformed allowlist fails closed. Public development access is
possible only with the explicit `TELEGRAM_ALLOW_ALL_DEVELOPMENT=true` switch.

## Public Bot API migration

Before using a bot token with a local server, the official server may require a
one-time `logOut` call against `https://api.telegram.org`. This application
never performs that call automatically.

To avoid placing the token in shell history, put the complete logout URL in a
temporary root-readable curl config file outside the repository:

```text
url = "https://api.telegram.org/bot<token>/logOut"
request = "POST"
```

Then run `curl --config /run/telegram-logout.conf` and securely remove the file.
Use the same single-server rule when moving between two local Bot API servers.

## Ubuntu dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3-venv tesseract-ocr tesseract-ocr-fas tesseract-ocr-eng
tesseract --version
tesseract --list-langs
```

The default OCR language is `fas+eng`, PSM is `6`, and preprocessing is
`autocontrast`. OCR is still only attempted on pages whose text layer is below
the configured threshold. Set `OCR_PREPROCESSING_MODE=none` for diagram-heavy
material when preprocessing is undesirable.

## Docker Compose

Copy `deploy/telegram/.env.example` to a protected file outside the repository
and run:

```bash
docker compose -f deploy/telegram/docker-compose.yml --env-file /etc/knowledge-builder/telegram.env up -d
docker compose -f deploy/telegram/docker-compose.yml logs -f knowledge-builder-bot
```

The Local Bot API port is published only on `127.0.0.1`. Inside Compose the bot
uses `http://telegram-bot-api:8081/bot` over the private network.

## systemd

Examples are in `deploy/systemd/`. Install them under `/etc/systemd/system`,
create a dedicated `knowledge-builder` user, and place secrets in
`/etc/knowledge-builder/telegram.env` with owner-only permissions.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-bot-api.service
sudo systemctl enable --now knowledge-builder-telegram.service
sudo journalctl -u knowledge-builder-telegram -f
```

Stop the bot with `sudo systemctl stop knowledge-builder-telegram`. The bot
stops accepting updates, waits briefly for queued work, and requests
cooperative cancellation rather than killing arbitrary OCR processes.

## Queue, cancellation, and restart policy

SQLite stores job metadata in `workspaces/telegram/jobs.sqlite3`. Default
concurrency is one and the in-memory queue is bounded. A failure is isolated to
its job. Queued cancellation is immediate; running cancellation is checked at
safe pipeline-stage boundaries.

After restart, persisted queued jobs are requeued. Jobs that were downloading,
processing, extracting, OCRing, or exporting are marked failed with the reason
`interrupted by bot restart`; they are not silently left running or
automatically rerun.

## Results and retention

The bot sends a Persian completion summary followed by existing JSON,
Markdown, Django seed, and knowledge-graph outputs when present. Output paths
must remain inside configured exporter directories. Large output groups are
placed into a traversal-safe ZIP; the source PDF is never included.

Telegram input copies and generated archives older than
`TELEGRAM_OUTPUT_RETENTION_HOURS` are removed at startup. Generated exporter
files remain reproducible and are governed by the repository's normal output
retention policy.

## Testing

```bash
python -m pytest -q
python -m pytest -q tests/test_telegram_config.py
python -m pytest -q tests/test_telegram_documents.py
python -m pytest -q tests/test_telegram_jobs.py
python -m pytest -q tests/test_ocr.py
```

Standard tests use fakes and never contact Telegram. Real checks are explicitly
marked:

```bash
python -m pytest -q -m ocr_integration
python -m pytest -q -m telegram_integration
```

The OCR integration test requires Tesseract, `fas+eng`, and a deterministic
Persian-capable font fixture. Telegram integration requires a disposable token,
allowlisted test account, and running local server; never use a production token
in automated tests.

## Troubleshooting

- `TELEGRAM_BOT_TOKEN is required`: supply it through the protected environment
  file.
- allowlist error: provide only positive numeric IDs separated by commas.
- connection refused on 8081: start the Local Bot API service and confirm its
  loopback binding.
- no updates after migration: call public Bot API `logOut` once and ensure the
  token is connected to only one Bot API server.
- OCR unavailable: run `tesseract --list-langs` and install `fas` and `eng`.
- disk rejection: increase free space or lower the configured reserve/size.
- interrupted job after restart: resend the file; interrupted CPU-heavy jobs are
  intentionally not rerun automatically.

## Security notes

The service is private by default, never logs tokens or captions, does not
process Telegram-controlled absolute paths directly, rejects symlinks and path
escapes, streams large files, uses atomic rename, validates output roots, and
keeps Local Bot API HTTP traffic on localhost/private networks. Rotate any token
that has been pasted into chat, terminal history, or an untrusted system.
