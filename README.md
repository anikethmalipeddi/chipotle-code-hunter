# chipotle-code-hunter

I made this because I got tired of watching Twitter for Chipotle free entree text-code drops.

It watches `@ChipotleTweets`, looks for promo/code tweets, pulls out the most likely code, makes noise, prints the tweet, copies the code, and opens Messages.

Auto-send is off by default. If you want the Mac to send the text through Messages, turn on `AUTO_SEND_MESSAGES=true`.

What it can do:

- monitor `@ChipotleTweets`
- use the official X API if you have a token
- optionally fall back to `ntscraper`/Nitter if you install it
- rate limit outbound requests
- detect likely promo tweets
- extract likely codes
- avoid repeats with a local seen file
- copy the code
- open Messages
- optionally send through Messages on macOS

Setup:

```bash
git clone https://github.com/anikethmalipeddi/chipotle-code-hunter.git
cd chipotle-code-hunter

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Before running it, either add `X_BEARER_TOKEN` to `.env` or install the optional Nitter fallback shown below.

Useful commands:

```bash
python3 main.py
python3 main.py --once
python3 main.py --test-detection
python3 main.py --show-config
DRY_RUN=true AUTO_SEND_MESSAGES=true python3 main.py --test-message DUNK23
```

Important `.env` stuff:

```env
TARGET_USERNAME=ChipotleTweets
SMS_NUMBER=888222

MONITOR_BACKEND=auto
X_BEARER_TOKEN=
REQUEST_MIN_INTERVAL_SECONDS=2

POLL_INTERVAL_SECONDS=30
FETCH_COUNT=5
DETECTION_THRESHOLD=6

AUTO_OPEN_MESSAGES=true
AUTO_SEND_MESSAGES=false
COPY_CODE_TO_CLIPBOARD=true
PLAY_SOUND=true
ALERT_SOUND=/System/Library/Sounds/Sosumi.aiff
ALERT_REPEAT_COUNT=3

STATE_FILE=.chipotle-code-hunter-seen.json
LOG_LEVEL=INFO
DRY_RUN=false
```

For the most reliable monitoring, use the official X API. Put the real token in your local `.env` file:

```env
MONITOR_BACKEND=auto
X_BEARER_TOKEN=
```

Do not commit your real `.env`. It is ignored by git.

If you do not have X API access, you can use the optional Nitter fallback:

```bash
python3 -m pip install ntscraper==0.4.0
```

Then leave `X_BEARER_TOKEN` blank. Public Nitter instances can be unreliable, so X API is still the better setup.

To enable auto-send on macOS:

```env
AUTO_SEND_MESSAGES=true
```

Test it safely first:

```bash
DRY_RUN=true AUTO_SEND_MESSAGES=true python3 main.py --test-message DUNK23
```

Then turn off `DRY_RUN` when you actually want it live. macOS may ask for permission to let Terminal/iTerm/Python control Messages. Your Mac also needs SMS forwarding set up.

Example alert:

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

Notes:

- `X_BEARER_TOKEN` and `.env` stay local.
- `--show-config` only says whether the token is configured. It does not print it.
- Nitter scraping can break.
- Auto-send is off by default.
- This is not affiliated with Chipotle or X.
- You are responsible for following any promo, carrier, Chipotle, and X rules.

If this helps you catch a drop, star it.
