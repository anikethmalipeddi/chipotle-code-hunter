#!/usr/bin/env python3
"""Monitor Chipotle tweets for likely text-to-claim promo code drops.

This tool is intentionally manual-assist only: it alerts, opens a Messages
draft, and copies the detected code. It does not send texts or redeem anything.
"""

import argparse
import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
from urllib.parse import quote


LOGGER = logging.getLogger("chipotle_code_hunter")

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
TWEET_ID_RE = re.compile(r"/status(?:es)?/(\d+)")
TOKEN_RE = re.compile(r"\b[A-Z0-9]{5,20}\b")


COMMON_NON_CODES = {
    "ABOUT",
    "ALERT",
    "AVAILABLE",
    "BASKETBALL",
    "BEFORE",
    "BURRITO",
    "CHIPOTLE",
    "CLAIM",
    "CINCO",
    "CODE",
    "COMEBACK",
    "COMMENT",
    "DINNER",
    "ENTREE",
    "FINAL",
    "FINALS",
    "FOLLOW",
    "FOOTBALL",
    "FREE",
    "GIVEAWAY",
    "GOING",
    "GREAT",
    "HAPPY",
    "HELLO",
    "LIMITED",
    "MESSAGE",
    "NATIONAL",
    "ONLINE",
    "ORDER",
    "PLAYOFFS",
    "PROMO",
    "REPLY",
    "RESTAURANT",
    "REWARD",
    "REWARDS",
    "SUPER",
    "SWEEPSTAKES",
    "THANKS",
    "TODAY",
    "TONIGHT",
    "TWEET",
    "TWEETS",
    "WHILE",
}


PROMO_SIGNALS: Sequence[Tuple[re.Pattern[str], float, str]] = (
    (re.compile(r"\btext(?:\s+us)?\b", re.IGNORECASE), 2.5, "text-to-claim language"),
    (re.compile(r"\b(?:send|message|reply)\b", re.IGNORECASE), 1.5, "message instruction"),
    (re.compile(r"\b(?:keyword|code|promo\s+code|claim\s+code)\b", re.IGNORECASE), 2.0, "code language"),
    (re.compile(r"\b(?:free|giveaway|give\s*away|drop|drops|dropped|claim|get yours|score)\b", re.IGNORECASE), 1.5, "giveaway language"),
    (re.compile(r"\b(?:entree|burrito|bowl|chips|guac|queso|meal)\b", re.IGNORECASE), 1.0, "Chipotle reward language"),
    (re.compile(r"\b(?:nba|finals|playoffs|super\s+bowl|cinco|mayo|burrito\s+day|game\s+day)\b", re.IGNORECASE), 1.0, "event context"),
    (re.compile(r"\b(?:now|today|tonight|limited|while\s+supplies\s+last|first\s+\d+)\b", re.IGNORECASE), 1.0, "urgency language"),
)


@dataclass(frozen=True)
class Config:
    target_username: str
    sms_number: str
    poll_interval_seconds: int
    fetch_count: int
    detection_threshold: float
    auto_open_messages: bool
    copy_code_to_clipboard: bool
    play_sound: bool
    alert_sound: str
    alert_repeat_count: int
    nitter_instance: Optional[str]
    ntscraper_log_level: Optional[int]
    state_file: Path
    log_level: str
    max_backoff_seconds: int
    dry_run: bool

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(Path(".env"))

        return cls(
            target_username=get_env("TARGET_USERNAME", "ChipotleTweets").lstrip("@"),
            sms_number=get_env("SMS_NUMBER", "888222"),
            poll_interval_seconds=get_int_env("POLL_INTERVAL_SECONDS", 30, minimum=5),
            fetch_count=get_int_env("FETCH_COUNT", 5, minimum=1),
            detection_threshold=get_float_env("DETECTION_THRESHOLD", 6.0, minimum=1.0),
            auto_open_messages=get_bool_env("AUTO_OPEN_MESSAGES", True),
            copy_code_to_clipboard=get_bool_env("COPY_CODE_TO_CLIPBOARD", True),
            play_sound=get_bool_env("PLAY_SOUND", True),
            alert_sound=get_env("ALERT_SOUND", "/System/Library/Sounds/Sosumi.aiff"),
            alert_repeat_count=get_int_env("ALERT_REPEAT_COUNT", 3, minimum=1),
            nitter_instance=blank_to_none(get_env("NITTER_INSTANCE", "")),
            ntscraper_log_level=get_optional_int_env("NTSCRAPER_LOG_LEVEL", 0),
            state_file=Path(get_env("STATE_FILE", ".chipotle-code-hunter-seen.json")),
            log_level=get_env("LOG_LEVEL", "INFO").upper(),
            max_backoff_seconds=get_int_env("MAX_BACKOFF_SECONDS", 300, minimum=10),
            dry_run=get_bool_env("DRY_RUN", False),
        )


@dataclass(frozen=True)
class Tweet:
    id: Optional[str]
    text: str
    url: Optional[str]
    created_at: Optional[str]
    raw: Dict[str, Any]

    @property
    def identity(self) -> str:
        if self.id:
            return self.id
        if self.url:
            return self.url
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        return "text:" + digest[:24]


@dataclass(frozen=True)
class CodeCandidate:
    code: str
    score: float
    reason: str


@dataclass(frozen=True)
class DetectionResult:
    should_alert: bool
    score: float
    code: Optional[str]
    reasons: List[str]
    candidate: Optional[CodeCandidate]


class TweetSource(Protocol):
    def fetch_latest(self, username: str, count: int) -> List[Tweet]:
        """Return recent tweets for username, newest first."""


class NitterTweetSource:
    """TweetSource backed by ntscraper.

    Nitter instances are fragile, so callers should treat fetch failures as
    temporary and retry with backoff.
    """

    def __init__(self, nitter_instance: Optional[str], log_level: Optional[int]) -> None:
        try:
            from ntscraper import Nitter
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: install requirements with `pip install -r requirements.txt`."
            ) from exc

        self._scraper = Nitter(log_level=log_level, skip_instance_check=False)
        self._instance = nitter_instance

    def fetch_latest(self, username: str, count: int) -> List[Tweet]:
        LOGGER.debug("Fetching %s latest tweets for @%s", count, username)
        response = self._scraper.get_tweets(
            username,
            mode="user",
            number=count,
            instance=self._instance,
            max_retries=2,
        )

        if not isinstance(response, dict):
            LOGGER.warning("Unexpected ntscraper response type: %s", type(response).__name__)
            return []

        raw_tweets = response.get("tweets") or []
        if not isinstance(raw_tweets, list):
            LOGGER.warning("Unexpected ntscraper tweets payload: %r", raw_tweets)
            return []

        tweets: List[Tweet] = []
        for raw in raw_tweets:
            if isinstance(raw, dict):
                tweet = parse_nitter_tweet(raw, username)
                if tweet.text:
                    tweets.append(tweet)

        return tweets


class SeenStore:
    def __init__(self, path: Path, max_entries: int = 1000) -> None:
        self.path = path
        self.max_entries = max_entries
        self._seen: List[str] = []
        self._seen_set = set()

    def load(self) -> None:
        if not self.path.exists():
            return

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not read seen-state file %s: %s", self.path, exc)
            return

        if isinstance(data, dict):
            items = data.get("seen", [])
        else:
            items = data

        if not isinstance(items, list):
            LOGGER.warning("Ignoring invalid seen-state file shape in %s", self.path)
            return

        self._seen = [str(item) for item in items[-self.max_entries :]]
        self._seen_set = set(self._seen)

    def has_seen(self, identity: str) -> bool:
        return identity in self._seen_set

    def mark_seen(self, identity: str) -> None:
        if identity in self._seen_set:
            return

        self._seen.append(identity)
        self._seen_set.add(identity)

        if len(self._seen) > self.max_entries:
            removed = self._seen[: -self.max_entries]
            self._seen = self._seen[-self.max_entries :]
            self._seen_set.difference_update(removed)

    def save(self) -> None:
        payload = {"seen": self._seen}
        try:
            self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            LOGGER.warning("Could not write seen-state file %s: %s", self.path, exc)


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a dependency."""
    if not path.exists():
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        LOGGER.warning("Could not read .env file: %s", exc)
        return

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def get_env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def blank_to_none(value: str) -> Optional[str]:
    return value if value else None


def get_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean value, got {raw!r}")


def get_int_env(name: str, default: int, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        value = default
    else:
        value = int(raw.strip())

    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def get_optional_int_env(name: str, default: Optional[int]) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    if raw.strip().lower() in {"none", "null"}:
        return None
    return int(raw.strip())


def get_float_env(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        value = default
    else:
        value = float(raw.strip())

    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_nitter_tweet(raw: Dict[str, Any], username: str) -> Tweet:
    text = str(raw.get("text") or raw.get("content") or "").strip()
    link = str(raw.get("link") or raw.get("url") or "").strip()
    tweet_id = extract_tweet_id(link)

    if tweet_id:
        url = f"https://x.com/{username}/status/{tweet_id}"
    elif link.startswith("http"):
        url = link
    elif link.startswith("/"):
        url = "https://x.com" + link
    else:
        url = None

    return Tweet(
        id=tweet_id or str(raw.get("id") or "").strip() or None,
        text=text,
        url=url,
        created_at=str(raw.get("date") or raw.get("created_at") or "").strip() or None,
        raw=raw,
    )


def extract_tweet_id(link: str) -> Optional[str]:
    match = TWEET_ID_RE.search(link)
    return match.group(1) if match else None


def detect_promo(text: str, sms_number: str, threshold: float) -> DetectionResult:
    score = 0.0
    reasons: List[str] = []

    for pattern, weight, reason in PROMO_SIGNALS:
        if pattern.search(text):
            score += weight
            reasons.append(reason)

    if normalize_digits(sms_number) and normalize_digits(sms_number) in normalize_digits(text):
        score += 2.0
        reasons.append(f"mentions destination {sms_number}")

    candidate = extract_best_code(text, sms_number)
    if candidate:
        code_boost = min(4.0, candidate.score / 2.0)
        score += code_boost
        reasons.append(f"code candidate {candidate.code} ({candidate.reason})")

    should_alert = candidate is not None and score >= threshold
    return DetectionResult(
        should_alert=should_alert,
        score=round(score, 2),
        code=candidate.code if candidate else None,
        reasons=reasons,
        candidate=candidate,
    )


def extract_best_code(text: str, sms_number: str) -> Optional[CodeCandidate]:
    sanitized = URL_RE.sub(" ", text)
    uppercase_text = sanitized.upper()
    sms_digits = normalize_digits(sms_number)
    candidates: List[CodeCandidate] = []

    contextual_patterns = [
        r"\bTEXT(?:\s+US)?\s+(?:THE\s+)?(?:CODE\s+)?([A-Z0-9]{5,20})\s+TO\b",
        r"\b(?:SEND|MESSAGE|REPLY)\s+(?:THE\s+)?(?:CODE\s+)?([A-Z0-9]{5,20})\b",
        r"\b(?:KEYWORD|CODE|PROMO\s+CODE|CLAIM\s+CODE)\s*(?:IS|=|:)?\s*([A-Z0-9]{5,20})\b",
    ]

    if sms_digits:
        contextual_patterns.append(r"\b([A-Z0-9]{5,20})\s+TO\s+" + re.escape(sms_digits) + r"\b")

    for pattern in contextual_patterns:
        for match in re.finditer(pattern, uppercase_text):
            raw_code = match.group(1)
            if is_valid_code(raw_code):
                candidates.append(
                    CodeCandidate(
                        code=raw_code,
                        score=9.0 + score_code_quality(raw_code),
                        reason="near text/code instruction",
                    )
                )

    for match in TOKEN_RE.finditer(uppercase_text):
        raw_code = match.group(0)
        if not is_valid_code(raw_code):
            continue
        if token_is_tagged_or_mentioned(sanitized, match.start()):
            continue

        context = uppercase_text[max(0, match.start() - 50) : match.end() + 50]
        context_score = 0.0
        if re.search(r"\b(TEXT|SEND|MESSAGE|REPLY|KEYWORD|CODE)\b", context):
            context_score += 3.0
        if sms_digits and sms_digits in normalize_digits(context):
            context_score += 2.0
        if re.search(r"\b(FREE|CLAIM|GIVEAWAY|DROP|ENTREE|BURRITO|BOWL)\b", context):
            context_score += 1.5

        candidate_score = score_code_quality(raw_code) + context_score
        if candidate_score >= 5.0:
            candidates.append(
                CodeCandidate(
                    code=raw_code,
                    score=candidate_score,
                    reason="uppercase alphanumeric candidate",
                )
            )

    if not candidates:
        return None

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[0]


def is_valid_code(value: str) -> bool:
    if not (5 <= len(value) <= 20):
        return False
    if not value.isalnum():
        return False
    if value.isdigit():
        return False
    if value in COMMON_NON_CODES:
        return False
    if re.fullmatch(r"20\d{2}", value):
        return False
    if re.fullmatch(r"\d{1,2}(?:AM|PM|ET|PT|EST|PST|CST|MST)", value):
        return False
    if re.fullmatch(r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{1,2}", value):
        return False
    return True


def score_code_quality(value: str) -> float:
    score = 0.0
    if any(char.isalpha() for char in value):
        score += 1.0
    if any(char.isdigit() for char in value):
        score += 2.5
    if value.isupper():
        score += 1.0
    if 6 <= len(value) <= 12:
        score += 1.5
    elif 5 <= len(value) <= 20:
        score += 0.5
    if value in COMMON_NON_CODES:
        score -= 4.0
    return score


def token_is_tagged_or_mentioned(text: str, start_index: int) -> bool:
    return start_index > 0 and text[start_index - 1] in {"#", "@"}


def normalize_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def process_tweet(tweet: Tweet, config: Config, seen_store: SeenStore) -> None:
    if seen_store.has_seen(tweet.identity):
        LOGGER.debug("Skipping already-seen tweet %s", tweet.identity)
        return

    result = detect_promo(tweet.text, config.sms_number, config.detection_threshold)
    seen_store.mark_seen(tweet.identity)
    seen_store.save()

    if result.should_alert and result.code:
        show_console_alert(tweet, result)
        alert_user(config, result.code)
        open_messages(config, result.code)
    else:
        LOGGER.info(
            "No alert for tweet %s (score %.2f): %s",
            tweet.identity,
            result.score,
            trim_for_log(tweet.text),
        )


def show_console_alert(tweet: Tweet, result: DetectionResult) -> None:
    line = "!" * 78
    print("\n" + line)
    print("CHIPOTLE PROMO CANDIDATE DETECTED")
    print(line)
    print(f"Code:       {result.code}")
    print(f"Score:      {result.score}")
    print(f"Reasons:    {', '.join(result.reasons)}")
    if tweet.url:
        print(f"Tweet URL:  {tweet.url}")
    if tweet.created_at:
        print(f"Tweet time: {tweet.created_at}")
    print("-" * 78)
    print(tweet.text)
    print(line + "\n")


def alert_user(config: Config, code: str) -> None:
    print("\a", end="", flush=True)

    if not config.play_sound:
        return
    if config.dry_run:
        LOGGER.info("DRY_RUN=true: would play alert sound %s", config.alert_sound)
        return

    sound_path = Path(config.alert_sound)
    if not sound_path.exists():
        LOGGER.warning("Alert sound does not exist: %s", sound_path)
        return

    for index in range(config.alert_repeat_count):
        try:
            subprocess.run(
                ["afplay", str(sound_path)],
                check=False,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            LOGGER.warning("Could not play alert sound on attempt %s: %s", index + 1, exc)
            break


def open_messages(config: Config, code: str) -> None:
    if config.copy_code_to_clipboard:
        copy_to_clipboard(code, config.dry_run)

    if not config.auto_open_messages:
        LOGGER.info("AUTO_OPEN_MESSAGES=false: not opening Messages")
        return
    if config.dry_run:
        LOGGER.info("DRY_RUN=true: would open Messages to %s with code %s", config.sms_number, code)
        return
    if platform.system() != "Darwin":
        LOGGER.warning("Messages integration is macOS-only. Copy the code manually: %s", code)
        return

    recipient = quote(config.sms_number, safe="+-.")
    body = quote(code)
    sms_url = f"sms:{recipient}&body={body}"

    try:
        subprocess.run(["open", sms_url], check=False)
    except OSError as exc:
        LOGGER.warning("Could not open Messages: %s", exc)


def copy_to_clipboard(text: str, dry_run: bool) -> None:
    if dry_run:
        LOGGER.info("DRY_RUN=true: would copy %s to clipboard", text)
        return

    try:
        subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        LOGGER.info("Copied detected code to clipboard")
    except OSError as exc:
        LOGGER.warning("Could not copy code to clipboard: %s", exc)


def trim_for_log(text: str, max_length: int = 120) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 3] + "..."


def monitor(config: Config, source: TweetSource, run_once: bool = False) -> None:
    seen_store = SeenStore(config.state_file)
    seen_store.load()

    LOGGER.info("Monitoring @%s every %ss", config.target_username, config.poll_interval_seconds)
    if config.dry_run:
        LOGGER.info("DRY_RUN=true: side effects are disabled")

    backoff_seconds = config.poll_interval_seconds

    while True:
        try:
            tweets = source.fetch_latest(config.target_username, config.fetch_count)
            LOGGER.info("Fetched %s tweet(s)", len(tweets))

            for tweet in reversed(tweets):
                process_tweet(tweet, config, seen_store)

            backoff_seconds = config.poll_interval_seconds

            if run_once:
                break

            time.sleep(config.poll_interval_seconds)
        except KeyboardInterrupt:
            LOGGER.info("Shutdown requested. Saving state and exiting.")
            seen_store.save()
            break
        except Exception:
            LOGGER.exception("Temporary monitoring failure")
            sleep_for = min(backoff_seconds, config.max_backoff_seconds)
            LOGGER.info("Retrying in %ss", sleep_for)
            time.sleep(sleep_for)
            backoff_seconds = min(backoff_seconds * 2, config.max_backoff_seconds)


def run_detection_self_test(config: Config) -> int:
    cases = [
        ("Text DUNK23 to 888222 for a free entree", True, "DUNK23"),
        ("Send FINALS25 now for a free burrito", True, "FINALS25"),
        ("NBA Finals start at 8PM ET", False, None),
        (
            "Tonight at 8PM ET: https://example.com/ABCDEF @CHIPOTLE #FREEBOWL 2026-06-05",
            False,
            None,
        ),
    ]

    failures = 0
    for text, expected_alert, expected_code in cases:
        result = detect_promo(text, config.sms_number, config.detection_threshold)
        passed = result.should_alert == expected_alert and result.code == expected_code
        status = "PASS" if passed else "FAIL"
        print(f"{status}: {text}")
        print(f"      alert={result.should_alert} code={result.code} score={result.score}")
        if not passed:
            failures += 1

    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor @ChipotleTweets for likely promo codes.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch and process one batch, then exit.",
    )
    parser.add_argument(
        "--test-detection",
        action="store_true",
        help="Run built-in detection/extraction sample checks without fetching tweets.",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print the resolved configuration and exit.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = Config.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    configure_logging(config.log_level)

    if args.show_config:
        print_config(config)
        return 0

    if args.test_detection:
        return 1 if run_detection_self_test(config) else 0

    try:
        source = NitterTweetSource(config.nitter_instance, config.ntscraper_log_level)
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        return 1

    monitor(config, source, run_once=args.once)
    return 0


def print_config(config: Config) -> None:
    redacted = {
        "target_username": config.target_username,
        "sms_number": config.sms_number,
        "poll_interval_seconds": config.poll_interval_seconds,
        "fetch_count": config.fetch_count,
        "detection_threshold": config.detection_threshold,
        "auto_open_messages": config.auto_open_messages,
        "copy_code_to_clipboard": config.copy_code_to_clipboard,
        "play_sound": config.play_sound,
        "alert_sound": config.alert_sound,
        "alert_repeat_count": config.alert_repeat_count,
        "nitter_instance": config.nitter_instance,
        "ntscraper_log_level": config.ntscraper_log_level,
        "state_file": str(config.state_file),
        "log_level": config.log_level,
        "max_backoff_seconds": config.max_backoff_seconds,
        "dry_run": config.dry_run,
    }
    print(json.dumps(redacted, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
