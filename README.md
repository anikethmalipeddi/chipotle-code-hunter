# chipotle-code-hunter

I made this because I got tired of staring at Twitter waiting for Chipotle to drop free entree codes.

`chipotle-code-hunter` is a small Python bot that watches `@ChipotleTweets` for likely text-to-claim promo drops. When it sees something that looks like a real code drop, it plays a loud alert, prints the tweet and detected code, opens macOS Messages to `888222`, and copies the code to your clipboard.

It does **not** send texts automatically, redeem promotions, create accounts, bypass rate limits, or try to game anything. You review the message and send it manually.

## Overview

Chipotle sometimes drops time-sensitive text-to-claim promos for events like NBA Finals, Super Bowl, Cinco de Mayo, National Burrito Day, and random giveaways. This project helps you notice those tweets quickly and prepare the text message faster.

The first version uses [`ntscraper`](https://pypi.org/project/ntscraper/) because the official X API is now pay-per-use and less practical for casual users. The code is still built around a small `TweetSource` interface, so a future official X API backend can be added without rewriting the detection and alerting logic.

## Features

- Monitors `@ChipotleTweets` continuously
- Uses scoring-based promo detection instead of one simple keyword match
- Extracts likely promo codes from text-to-claim language
- Avoids obvious non-codes like URLs, usernames, hashtags, dates, times, and generic words
- Prevents duplicate alerts with a local seen-state file
- Handles temporary scraper/network failures with exponential backoff
- Plays a loud local alert sound
- Prints a highly visible console alert
- Opens macOS Messages with the detected code attempted in the SMS URL
- Copies the code to your clipboard as a fallback
- Keeps all personal settings configurable through environment variables

## How It Works

The bot polls recent tweets from the target account, then runs each new tweet through two passes:

1. Promo scoring checks for text-to-claim language, giveaway terms, Chipotle reward words, event context, urgency, and the configured SMS destination.
2. Code extraction looks for strong contextual patterns such as `text DUNK23 to 888222`, `send FINALS25`, and `keyword BURRITO24`.

If the tweet score crosses your threshold and a reasonable code candidate is found, the bot alerts you.

The Messages integration uses the `sms:` URL scheme and also copies the code to your clipboard. Apple documents the `sms:` scheme for opening Messages, but its archived docs do not promise reliable body prefill, so the clipboard fallback is intentional.

## Setup

1. Clone the repo:

   ```bash
   git clone https://github.com/YOUR_USERNAME/chipotle-code-hunter.git
   cd chipotle-code-hunter
   ```

2. Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install requirements:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:

   ```bash
   cp .env.example .env
   ```

   Edit `.env` if you want to change the monitored account, polling interval, alert sound, or SMS destination.

5. Run the bot:

   ```bash
   python3 main.py
   ```

## Usage

Run continuously:

```bash
python3 main.py
```

Run one polling pass and exit:

```bash
python3 main.py --once
```

Test the detection logic without fetching tweets:

```bash
python3 main.py --test-detection
```

Print the resolved configuration:

```bash
python3 main.py --show-config
```

For a safe test run with side effects disabled:

```bash
DRY_RUN=true AUTO_OPEN_MESSAGES=false PLAY_SOUND=false python3 main.py --test-detection
```

## Configuration

All settings can be placed in `.env` or exported in your shell.

| Variable | Default | Description |
| --- | --- | --- |
| `TARGET_USERNAME` | `ChipotleTweets` | X/Twitter account to monitor, without `@`. |
| `SMS_NUMBER` | `888222` | Destination number for text-to-claim promos. |
| `POLL_INTERVAL_SECONDS` | `30` | Seconds between polling attempts. Minimum is 5. |
| `FETCH_COUNT` | `5` | Number of recent tweets to fetch per poll. |
| `DETECTION_THRESHOLD` | `6` | Alert threshold. Raise it for fewer alerts, lower it for more. |
| `AUTO_OPEN_MESSAGES` | `true` | Open macOS Messages when a likely code is found. |
| `COPY_CODE_TO_CLIPBOARD` | `true` | Copy the detected code to the clipboard. |
| `PLAY_SOUND` | `true` | Play the configured alert sound. |
| `ALERT_SOUND` | `/System/Library/Sounds/Sosumi.aiff` | Sound file used by `afplay` on macOS. |
| `ALERT_REPEAT_COUNT` | `3` | Number of times to play the alert sound. |
| `NITTER_INSTANCE` | empty | Optional specific Nitter instance. Leave blank to let `ntscraper` choose. |
| `NTSCRAPER_LOG_LEVEL` | `0` | Logging level passed to `ntscraper`. |
| `STATE_FILE` | `.chipotle-code-hunter-seen.json` | Local file used to avoid duplicate alerts. |
| `LOG_LEVEL` | `INFO` | Python logging level. |
| `MAX_BACKOFF_SECONDS` | `300` | Maximum retry delay after temporary failures. |
| `DRY_RUN` | `false` | Disable sounds, clipboard writes, and Messages opening. |

## Example Output

```text
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
CHIPOTLE PROMO CANDIDATE DETECTED
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
Code:       DUNK23
Score:      10.5
Reasons:    text-to-claim language, giveaway language, Chipotle reward language, mentions destination 888222, code candidate DUNK23
Tweet URL:  https://x.com/ChipotleTweets/status/1234567890
------------------------------------------------------------------------------
Text DUNK23 to 888222 for a free entree while supplies last.
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

## Limitations

This project depends on a scraper backend. Scrapers can break when X changes its site, when Nitter instances go down, or when public instances get overloaded. `ntscraper` itself warns that Nitter availability can be unreliable.

The official X API is cleaner and more stable, but it currently uses pay-per-use pricing for reads. That is why the first version defaults to scraping while keeping the monitoring backend modular.

The Messages body prefill is best-effort. The bot copies the code to your clipboard because the `sms:` URL scheme may not reliably prefill message text on every macOS version.

## Disclaimer

- This is a personal-use helper tool.
- Users are responsible for complying with X, Chipotle, carrier, and promotion terms.
- Scraping approaches may break over time.
- No automatic redemption occurs.
- No text messages are sent automatically.
- This project is not affiliated with Chipotle or X.

## Contributing

Pull requests are welcome. Good contributions include:

- Better promo detection examples
- A clean official X API `TweetSource`
- More reliable scraper support
- Tests for tricky code extraction cases
- Documentation improvements

Please keep the project focused on manual alerts and manual review. Anything that auto-sends, auto-redeems, bypasses limits, or creates unfair access is out of scope.

## Star Request

If this saves you from staring at a timeline during a promo drop, please star the repo. It helps other people find it too.
