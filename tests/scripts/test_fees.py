"""The fee-tier and pair-rules poller, `scripts/recording/fees.py`.

Loaded by path: it is a standalone script and must not become a package. Kraken is
a stub transport; nothing here touches the network, and no credential used here is
real — the key pair below is made up for the test and signs nothing Kraken sees.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import urllib.parse
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FEES_PY = REPO_ROOT / "scripts" / "recording" / "fees.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("acsoe_fees_script", FEES_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fees = _load()

KEY = "test-key-not-real-0123456789"
SECRET = base64.b64encode(b"test-secret-not-real-" * 3).decode()
ACCOUNT_VOLUME = "98765.4321"

ASSET_PAIRS = {
    "error": [],
    "result": {
        "XXBTZUSD": {"altname": "XBTUSD", "wsname": "XBT/USD", "ordermin": "0.00005"},
        "XETHZUSD": {"altname": "ETHUSD", "wsname": "ETH/USD", "ordermin": "0.001"},
        "XDGUSD": {"altname": "XDGUSD", "wsname": "XDG/USD", "ordermin": "40"},
        "ETHXBT": {"altname": "ETHXBT", "wsname": "ETH/XBT", "ordermin": "0.001"},
    },
}


def _trade_volume(pairs: list[str]) -> dict[str, Any]:
    row = {"fee": "0.8000", "minfee": "0.1000", "maxfee": "0.8000", "nextfee": "0.7000",
           "tiervolume": "0.0000", "nextvolume": "10000.0000"}
    return {
        "error": [],
        "result": {
            "asset_class": "currency",
            "currency": "ZUSD",
            "volume": ACCOUNT_VOLUME,
            "inputs": {"domain_spot_volume_30d": ACCOUNT_VOLUME},
            "fees": {pair: dict(row) for pair in pairs},
            "fees_maker": {pair: dict(row, fee="0.4000") for pair in pairs},
        },
    }


class Kraken:
    """A stub transport. Answers from scripted envelopes and keeps every request."""

    def __init__(
        self,
        *,
        asset_pairs: list[Any] | None = None,
        trade_volume: list[Any] | None = None,
    ) -> None:
        self.asset_pairs = list(asset_pairs if asset_pairs is not None else [ASSET_PAIRS])
        self.trade_volume = trade_volume
        self.requests: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> bytes:
        self.requests.append((method, url, dict(headers), body))
        if url.endswith(fees.ASSET_PAIRS_PATH):
            answer = self.asset_pairs.pop(0) if len(self.asset_pairs) > 1 else self.asset_pairs[0]
        else:
            assert body is not None
            form = urllib.parse.parse_qs(body.decode())
            if self.trade_volume:
                answer = self.trade_volume.pop(0)
            else:
                answer = _trade_volume(form["pair"][0].split(","))
        if isinstance(answer, Exception):
            raise answer
        return json.dumps(answer).encode()

    def private(self) -> list[tuple[str, str, dict[str, str], bytes | None]]:
        return [request for request in self.requests if request[0] == "POST"]


def _env(tmp_path: Path, text: str | None = None) -> Path:
    path = tmp_path / ".env"
    path.write_text(
        text if text is not None else f'KRAKEN_API_KEY={KEY}\nKRAKEN_API_SECRET="{SECRET}"\n',
        encoding="utf-8",
    )
    return path


def _lines(directory: Path) -> list[dict[str, Any]]:
    return [
        json.loads(raw)
        for path in sorted(directory.glob("fees__*.jsonl"))
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip()
    ]


def _poller(tmp_path: Path, kraken: Kraken, env: Path | None) -> Any:
    writer = fees.JsonlWriter(tmp_path / "out", prefix="fees", source_id="test")
    return fees.Poller(writer, env_file=env, transport=kraken, sleep=lambda _s: None)


# --------------------------------------------------------------------------- #
# Credentials and signing
# --------------------------------------------------------------------------- #


def test_the_signer_is_the_package_signer() -> None:
    """A copy, kept equal. If the package's scheme changes and this one does not,
    this is where it goes red rather than in an hourly gap marker."""
    from acsoe.clients.kraken.rest import sign_request

    form = {"pair": "XXBTZUSD,XETHZUSD", "fee_schedule": "true"}
    for nonce in (1, 1_758_252_000_000_000, 1_758_252_000_000_001):
        assert fees.sign_request(
            path=fees.TRADE_VOLUME_PATH, nonce=nonce, form=form, secret=SECRET
        ) == sign_request(path=fees.TRADE_VOLUME_PATH, nonce=nonce, form=form, secret=SECRET)


def test_only_the_two_names_are_read_from_env_and_the_environment_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KRAKEN_API_KEY", "from-the-environment")
    monkeypatch.setenv("KRAKEN_API_SECRET", "from-the-environment")
    env = _env(
        tmp_path,
        "# a comment\nexport KRAKEN_API_KEY='k1'\nOTHER_SECRET=nope\nKRAKEN_API_SECRET=\"s1\"\n",
    )
    credentials = fees.read_credentials(env)
    assert credentials is not None
    assert (credentials.key, credentials.secret) == ("k1", "s1")
    assert not hasattr(credentials, "OTHER_SECRET")
    assert "k1" not in repr(credentials) and "s1" not in str(credentials)


@pytest.mark.parametrize(
    "text",
    ["", "KRAKEN_API_KEY=k1\n", "KRAKEN_API_SECRET=s1\n", "KRAKEN_API_KEY=\nKRAKEN_API_SECRET=s\n"],
)
def test_a_missing_half_of_the_pair_is_no_credentials(tmp_path: Path, text: str) -> None:
    assert fees.read_credentials(_env(tmp_path, text)) is None


def test_no_env_file_is_no_credentials(tmp_path: Path) -> None:
    assert fees.read_credentials(None) is None
    assert fees.read_credentials(tmp_path / "absent.env") is None


def test_the_nonce_counts_microseconds_and_never_repeats() -> None:
    """The daemon's client counts microseconds on the same key. A millisecond nonce
    would sit below it and be refused for ever."""
    real = fees.Nonce()
    assert real.next() > 10**15
    frozen = fees.Nonce(clock=lambda: 5)
    assert [frozen.next(), frozen.next(), frozen.next()] == [5, 6, 7]


def test_redact_removes_both_values() -> None:
    credentials = fees.Credentials(key=KEY, secret=SECRET)
    text = fees.redact(f"bad {KEY} and {SECRET} here", credentials)
    assert KEY not in text and SECRET not in text
    assert text.count(fees.REDACTED) == 2


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #


def test_v2_symbols_map_to_rest_keys_through_wsname_and_the_aliases() -> None:
    mapped, unmatched = fees.rest_names(
        ["BTC/USD", "ETH/USD", "DOGE/USD", "ETH/BTC", "ZZZ/USD"], ASSET_PAIRS["result"]
    )
    assert mapped == {
        "BTC/USD": "XXBTZUSD",
        "ETH/USD": "XETHZUSD",
        "DOGE/USD": "XDGUSD",
        "ETH/BTC": "ETHXBT",
    }
    assert unmatched == ["ZZZ/USD"]


# --------------------------------------------------------------------------- #
# One poll
# --------------------------------------------------------------------------- #


def test_a_poll_records_both_answers_verbatim(tmp_path: Path) -> None:
    kraken = Kraken()
    poller = _poller(tmp_path, kraken, _env(tmp_path))
    summary = poller.poll(["BTC/USD", "ETH/USD", "ZZZ/USD"], slot="2026-09-19T05:00:00.000000Z")
    poller.writer.close()

    lines = _lines(tmp_path / "out")
    assert [line["channel"] for line in lines] == ["asset_pairs", "trade_volume"]
    assert lines[0]["payload"]["response"] == ASSET_PAIRS
    trade = lines[1]["payload"]
    assert trade["response"] == _trade_volume(["XXBTZUSD", "XETHZUSD"])
    assert trade["request"] == {"pair": ["XXBTZUSD", "XETHZUSD"], "fee_schedule": "true"}
    assert trade["pairs"] == {"BTC/USD": "XXBTZUSD", "ETH/USD": "XETHZUSD"}
    assert trade["unmatched"] == ["ZZZ/USD"]

    (_method, url, headers, body) = kraken.private()[0]
    assert url == fees.REST_URL + fees.TRADE_VOLUME_PATH
    assert headers["API-Key"] == KEY
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert body is not None
    form = urllib.parse.parse_qs(body.decode())
    assert form["pair"] == ["XXBTZUSD,XETHZUSD"]
    assert form["fee_schedule"] == ["true"]
    nonce = int(form["nonce"][0])
    assert headers["API-Sign"] == fees.sign_request(
        path=fees.TRADE_VOLUME_PATH,
        nonce=nonce,
        form={"pair": "XXBTZUSD,XETHZUSD", "fee_schedule": "true"},
        secret=SECRET,
    )

    assert summary["trade_volume"] == {
        "result_keys": ["asset_class", "currency", "fees", "fees_maker", "inputs", "volume"],
        "fees_pairs": ["XETHZUSD", "XXBTZUSD"],
        "schedules_returned": False,
    }


def test_nothing_written_or_printed_carries_a_secret_or_the_volume_outside_the_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    refused = {"error": [f"EAPI:Invalid key {KEY}"], "result": {}}
    kraken = Kraken(trade_volume=[refused, refused, refused, refused, refused])
    poller = _poller(tmp_path, kraken, _env(tmp_path))
    summary = poller.poll(["BTC/USD"], slot="s1")
    poller.writer.close()

    archive = b"".join(path.read_bytes() for path in (tmp_path / "out").glob("*.jsonl"))
    captured = capsys.readouterr()
    (_method, _url, headers, body) = kraken.private()[0]
    assert body is not None
    nonce = urllib.parse.parse_qs(body.decode())["nonce"][0]
    for secret in (KEY, SECRET, headers["API-Sign"], nonce):
        assert secret not in captured.err, "a credential, signature or nonce reached stderr"
        assert secret not in captured.out
        assert secret.encode() not in archive, "a credential, signature or nonce reached the archive"
        assert secret not in json.dumps(summary)
    gap = _lines(tmp_path / "out")[-1]
    assert gap["kind"] == "gap"
    assert gap["payload"]["call"] == "trade_volume"
    assert fees.REDACTED in gap["payload"]["reason"]

    # And a successful poll's summary names keys, never the account's volume.
    ok = _poller(tmp_path / "second", Kraken(), _env(tmp_path))
    printed = json.dumps(ok.poll(["BTC/USD"], slot="s2"))
    assert ACCOUNT_VOLUME not in printed


def test_no_credentials_still_records_asset_pairs_and_writes_a_gap(tmp_path: Path) -> None:
    kraken = Kraken()
    poller = _poller(tmp_path, kraken, None)
    summary = poller.poll(["BTC/USD"], slot="s1")
    poller.writer.close()
    lines = _lines(tmp_path / "out")
    assert [line["channel"] for line in lines] == ["asset_pairs", "_recorder"]
    assert lines[1]["kind"] == "gap"
    assert "credentials not set" in lines[1]["payload"]["reason"]
    assert kraken.private() == [], "a private call was made with no credentials"
    assert summary["trade_volume"] == "no credentials"


def test_a_refused_call_is_retried_then_written_as_a_gap(tmp_path: Path) -> None:
    refused = {"error": ["EAPI:Invalid nonce"], "result": {}}
    sleeps: list[float] = []
    kraken = Kraken(trade_volume=[refused] * 5)
    writer = fees.JsonlWriter(tmp_path / "out", prefix="fees", source_id="test")
    poller = fees.Poller(writer, env_file=_env(tmp_path), transport=kraken, sleep=sleeps.append)
    poller.poll(["BTC/USD"], slot="s1")
    writer.close()
    assert len(kraken.private()) == 5
    assert sleeps == list(fees.RETRY_DELAYS_S)
    gap = _lines(tmp_path / "out")[-1]
    assert gap["payload"] == {
        "poller": "fees",
        "call": "trade_volume",
        "slot": "s1",
        "reason": "Kraken refused: EAPI:Invalid nonce",
        "attempts": 5,
    }


def test_a_refusal_then_success_records_the_success_and_no_gap(tmp_path: Path) -> None:
    refused = {"error": ["EAPI:Invalid nonce"], "result": {}}
    kraken = Kraken(trade_volume=[refused, _trade_volume(["XXBTZUSD"])])
    poller = _poller(tmp_path, kraken, _env(tmp_path))
    poller.poll(["BTC/USD"], slot="s1")
    poller.writer.close()
    kinds = [(line["kind"], line["channel"]) for line in _lines(tmp_path / "out")]
    assert kinds == [("tick", "asset_pairs"), ("tick", "trade_volume")]
    nonces = [
        int(urllib.parse.parse_qs(body.decode())["nonce"][0])
        for (_m, _u, _h, body) in kraken.private()
        if body is not None
    ]
    assert nonces[1] > nonces[0], "a retry reused its nonce"


def test_an_asset_pairs_outage_keeps_the_last_name_map(tmp_path: Path) -> None:
    down = fees.PollError("URLError: down")
    kraken = Kraken(asset_pairs=[ASSET_PAIRS, down, down, down, down, down, ASSET_PAIRS])
    poller = _poller(tmp_path, kraken, _env(tmp_path))
    poller.poll(["BTC/USD"], slot="s1")
    second = poller.poll(["BTC/USD"], slot="s2")
    poller.writer.close()
    channels = [(line["kind"], line["channel"]) for line in _lines(tmp_path / "out")]
    assert channels == [
        ("tick", "asset_pairs"),
        ("tick", "trade_volume"),
        ("gap", "_recorder"),
        ("tick", "trade_volume"),
    ]
    assert second["asset_pairs"] == "failed"


def test_with_no_name_map_ever_the_fee_is_a_gap_not_a_guess(tmp_path: Path) -> None:
    down = fees.PollError("URLError: down")
    kraken = Kraken(asset_pairs=[down] * 6)
    poller = _poller(tmp_path, kraken, _env(tmp_path))
    poller.poll(["BTC/USD"], slot="s1")
    poller.writer.close()
    lines = _lines(tmp_path / "out")
    assert [line["payload"]["call"] for line in lines] == ["asset_pairs", "trade_volume"]
    assert kraken.private() == []


def test_a_non_envelope_is_a_poll_error() -> None:
    for body in (b"not json", b"[]", b'{"result": {}}', b'{"error": "x"}', b'{"error": [], "result": 1}'):
        with pytest.raises(fees.PollError):
            fees.parse_envelope(body)


# --------------------------------------------------------------------------- #
# The process
# --------------------------------------------------------------------------- #


def _heartbeat(archive: Path, pairs: list[str]) -> None:
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "heartbeat__test__2026-09-19.ndjson").write_text(
        json.dumps({"tier": "tier1", "pairs": pairs}) + "\n", encoding="utf-8"
    )


def test_once_runs_end_to_end_with_session_markers(tmp_path: Path) -> None:
    archive = tmp_path / "raw"
    _heartbeat(archive, ["BTC/USD", "ETH/USD"])
    env = _env(tmp_path)
    args = fees.parse_args(
        ["--archive", str(archive), "--source-id", "test", "--env-file", str(env), "--once"]
    )
    kraken = Kraken()
    assert fees.run(args, transport=kraken, sleep=lambda _s: None) == 0
    lines = _lines(archive / "fees")
    kinds = [(line["kind"], line["channel"]) for line in lines]
    assert kinds == [
        ("tick", "asset_pairs"),
        ("tick", "trade_volume"),
        ("session", "_recorder"),
        ("session", "_recorder"),
    ]
    start = lines[2]["payload"]
    assert start["event"] == "start"
    assert start["spot_pairs"] == ["BTC/USD", "ETH/USD"]
    assert start["first_poll"]["trade_volume"]["schedules_returned"] is False
    assert lines[3]["payload"]["event"] == "stop"


def test_a_held_lock_exits_two_for_the_supervisor(tmp_path: Path) -> None:
    out = tmp_path / "fees"
    with fees.ArchiveLock(out.resolve()):
        code = fees.main(["--out", str(out), "--pairs", "BTC/USD", "--once", "--source-id", "t"])
    assert code == 2


def test_the_script_imports_nothing_from_the_package_or_its_neighbours() -> None:
    for line in FEES_PY.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "acsoe" not in stripped, stripped
            assert "funding" not in stripped and "record" not in stripped, stripped
