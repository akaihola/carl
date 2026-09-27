import hashlib
import hmac
import math
import re

import pytest

from carl import cli
from carl.gate import SYLLABLES, GateError, Passes, generate_passphrase, hash_password

from .conftest import OTHER_PASSWORD, PASSWORD, TOKEN_SECRET


def test_an_entry_is_salt_and_scrypt_hash():
    entry = hash_password(PASSWORD, "0123456789abcdef")
    salt, digest = entry.split(":")
    assert salt == "0123456789abcdef"
    expected = hashlib.scrypt(PASSWORD.encode(), salt=salt.encode(), n=2**14, r=8, p=1)
    assert digest == expected.hex()


def test_each_entry_gets_its_own_salt():
    assert hash_password(PASSWORD).split(":")[0] != hash_password(PASSWORD).split(":")[0]


def test_a_generated_passphrase_is_four_words_of_about_72_bits():
    passphrase = generate_passphrase()
    words = passphrase.split("-")
    assert len(words) == 4
    assert all(re.fullmatch(r"([bdfgklmnprstv][aeiou]){3}", w) for w in words)
    assert math.log2(len(SYLLABLES) ** 12) > 72
    assert generate_passphrase() != passphrase


def test_a_pass_matches_its_own_entry(passes, entries):
    salts = [e.split(":")[0] for e in entries.split(",")]
    assert passes.check(PASSWORD) == salts[0]
    assert passes.check(OTHER_PASSWORD) == salts[1]
    assert passes.check("bakodi-sulema-rotike-fanupb") is None
    assert passes.check("") is None


def test_the_cookie_is_hmac_of_the_entrys_salt(passes):
    salt = passes.check(PASSWORD)
    token = passes.token(salt)
    assert token == hmac.new(TOKEN_SECRET.encode(), salt.encode(), hashlib.sha256).hexdigest()
    assert passes.valid(token)
    assert not passes.valid(token[:-1] + "0" if token[-1] != "0" else token[:-1] + "1")
    assert not passes.valid("")
    assert not passes.valid(None)


def test_deleting_an_entry_revokes_only_that_pass(entries):
    first, second = entries.split(",")
    passes = Passes(entries, TOKEN_SECRET)
    first_token = passes.token(passes.check(PASSWORD))
    second_token = passes.token(passes.check(OTHER_PASSWORD))
    after = Passes(second, TOKEN_SECRET)
    assert not after.valid(first_token)
    assert after.valid(second_token)


def test_rotating_the_token_secret_revokes_every_pass(passes, entries):
    token = passes.token(passes.check(PASSWORD))
    assert not Passes(entries, "y" * 40).valid(token)


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"CARL_PASSWORDS": "", "TOKEN_SECRET": TOKEN_SECRET},
        {"CARL_PASSWORDS": hash_password(PASSWORD)},
        {"CARL_PASSWORDS": hash_password(PASSWORD), "TOKEN_SECRET": "short"},
        {"CARL_PASSWORDS": PASSWORD, "TOKEN_SECRET": TOKEN_SECRET},
        {"CARL_PASSWORDS": "abc:def", "TOKEN_SECRET": TOKEN_SECRET},
    ],
)
def test_carl_never_runs_without_valid_passes(environ):
    with pytest.raises(GateError):
        Passes.from_env(environ)


def test_passes_from_the_environment():
    entry = hash_password(PASSWORD)
    passes = Passes.from_env({"CARL_PASSWORDS": f" {entry} ,", "TOKEN_SECRET": TOKEN_SECRET})
    assert passes.check(PASSWORD) == entry.split(":")[0]


def test_hash_password_command_makes_a_working_entry(capsys):
    assert cli.main(["hash-password", PASSWORD]) == 0
    out = capsys.readouterr().out
    entry = re.search(r"entry:\s+(\S+)", out).group(1)
    assert Passes(entry, TOKEN_SECRET).check(PASSWORD)


def test_hash_password_command_generates_a_passphrase(capsys):
    assert cli.main(["hash-password"]) == 0
    out = capsys.readouterr().out
    passphrase = re.search(r"access pass:\s+(\S+)", out).group(1)
    entry = re.search(r"entry:\s+(\S+)", out).group(1)
    assert len(passphrase.split("-")) == 4
    assert Passes(entry, TOKEN_SECRET).check(passphrase)


def test_hash_password_command_refuses_a_short_pass():
    with pytest.raises(SystemExit):
        cli.main(["hash-password", "too-short"])
