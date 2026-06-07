# chipotle-code-hunter

I got tired of watching Twitter every time Chipotle did one of those free entree text-code drops, so I made this.

This is a small Python script that watches `@ChipotleTweets`. If a tweet looks like a text-to-claim promo, it tries to pull out the code, makes noise, prints the tweet, copies the code, and opens Messages.

By default it does not send the text. If you want it to send through Messages automatically on macOS, set `AUTO_SEND_MESSAGES=true` in `.env`.

## What it does

- Watches `@ChipotleTweets`
- Looks for likely promo/code tweets
- Tries to extract the best code
- Avoids obvious junk like URLs, hashtags, usernames, dates, and times
- Plays a loud alert
- Prints the tweet and code in the terminal
- Opens macOS Messages to `888222`
- Can auto-send through Messages if you turn that on
- Copies the code to your clipboard
- Remembers tweets it already checked so it does not keep alerting on the same thing

## Monitoring backend

Best setup: use the official X API if you have a bearer token.

```env
MONITOR_BACKEND=auto
X_BEARER_TOKEN=your_token_here
```

If you do not set `X_BEARER_TOKEN`, it falls back to [`ntscraper`](https://pypi.org/project/ntscraper/). That works without an API key, but it depends on public Nitter instances, which can be flaky.

You can force either one:

```env
MONITOR_BACKEND=x_api
```

or:

```env
MONITOR_BACKEND=nitter
```

## Setup

```bash
git clone https://github.com/anikethmalipeddi/chipotle-code-hunter.git
cd chipotle-code-hunter

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
python3 main.py
```

Edit `.env` if you want to change the account, phone number, polling time, alert sound, or anything else.

## Usage

Run normally:

```bash
python3 main.py
```

Run one check and exit:

```bash
python3 main.py --once
```

Test the code detection logic:

```bash
python3 main.py --test-detection
```

Show your current config:

```bash
python3 main.py --show-config
```

Safe dry run:

```bash
DRY_RUN=true AUTO_OPEN_MESSAGES=false PLAY_SOUND=false python3 main.py --once
```

Test the Messages/send path without fetching tweets:

```bash
DRY_RUN=true AUTO_SEND_MESSAGES=true python3 main.py --test-message DUNK23
```

Actually enable auto-send:

```env
AUTO_SEND_MESSAGES=true
```

## Config

These go in `.env`.

| Variable | Default | What it does |
| --- | --- | --- |
| `TARGET_USERNAME` | `ChipotleTweets` | Account to watch, without `@`. |
| `SMS_NUMBER` | `888222` | Text-to-claim number. |
| `MONITOR_BACKEND` | `auto` | `auto`, `x_api`, or `nitter`. |
| `X_BEARER_TOKEN` | empty | Official X API bearer token. Used when set. |
| `POLL_INTERVAL_SECONDS` | `30` | How often to check. |
| `FETCH_COUNT` | `5` | How many recent tweets to look at. |
| `DETECTION_THRESHOLD` | `6` | Higher = fewer alerts, lower = more alerts. |
| `AUTO_OPEN_MESSAGES` | `true` | Opens Messages when a code is found. |
| `AUTO_SEND_MESSAGES` | `false` | Sends the code through macOS Messages automatically. Requires Messages/SMS forwarding and macOS automation permission. |
| `COPY_CODE_TO_CLIPBOARD` | `true` | Copies the code after detection. |
| `PLAY_SOUND` | `true` | Plays the alert sound. |
| `ALERT_SOUND` | `/System/Library/Sounds/Sosumi.aiff` | Sound file for the alert. |
| `ALERT_REPEAT_COUNT` | `3` | How many times to play the sound. |
| `NITTER_INSTANCE` | empty | Optional Nitter instance. |
| `NTSCRAPER_LOG_LEVEL` | `0` | Log level for `ntscraper`. |
| `STATE_FILE` | `.chipotle-code-hunter-seen.json` | Local file for already-seen tweets. |
| `LOG_LEVEL` | `INFO` | App log level. |
| `MAX_BACKOFF_SECONDS` | `300` | Max retry delay after errors. |
| `DRY_RUN` | `false` | Disables sounds, clipboard writes, and Messages. |

## Example output

```text
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
CHIPOTLE PROMO CANDIDATE DETECTED
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Code:       DUNK23
Score:      10.5
Tweet URL:  https://x.com/ChipotleTweets/status/1234567890
------------------------------------------------------------------------------
Text DUNK23 to 888222 for a free entree while supplies last.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

## Notes

The official X API is the reliable option if you have access to it. The no-key scraper fallback can break if X changes things or if public Nitter instances are down.

Also, the Messages prefill is best-effort. The script opens the `sms:` link and also copies the code because macOS does not always prefill the message body reliably.

If `AUTO_SEND_MESSAGES=true`, the script uses AppleScript to send through the macOS Messages app. You may need to let Terminal/iTerm/Python control Messages in System Settings. Your Mac also has to be able to send SMS messages through Messages.

To test that setup without sending anything, keep `DRY_RUN=true` and run:

```bash
DRY_RUN=true AUTO_SEND_MESSAGES=true python3 main.py --test-message DUNK23
```

Once that looks right, set `DRY_RUN=false` in `.env` for the real thing.

## Disclaimer

This is just a personal helper script. You are responsible for following Chipotle, X, carrier, and promo rules.

Automatic sending is off by default. If you enable it, that is on you. This project is not affiliated with Chipotle or X.

## Contributing

PRs are welcome. Useful stuff would be better detection examples, tests, a cleaner tweet source, or an official X API backend.

If this helps you catch a drop, star the repo.
