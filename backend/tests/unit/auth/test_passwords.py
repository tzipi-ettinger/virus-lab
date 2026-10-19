import pytest

from app.auth.passwords import dummy_hash, hash_password, verify_password


def test_right_password_matches():
    assert verify_password("correct horse battery", hash_password("correct horse battery"))


def test_wrong_password_does_not_match():
    assert not verify_password("correct horse batterY", hash_password("correct horse battery"))


def test_same_password_gets_a_new_salt_each_time():
    assert hash_password("correct horse battery") != hash_password("correct horse battery")


def test_hash_does_not_contain_the_password():
    assert "battery" not in hash_password("correct horse battery")


@pytest.mark.parametrize(
    "stored",
    [
        "",
        "plain",
        "bcrypt$1$2$3$c2FsdA==$aGFzaA==",
        "scrypt$x$8$1$c2FsdA==$aGFzaA==",
        "scrypt$16384$8$1$!!$aGFzaA==",
    ],
)
def test_malformed_hash_is_a_mismatch_not_an_error(stored):
    assert not verify_password("anything", stored)


def test_dummy_hash_is_a_valid_hash_no_password_matches():
    assert dummy_hash().startswith("scrypt$")
    assert not verify_password("", dummy_hash())
