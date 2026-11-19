"""Input validation rules for POST /posting."""

from __future__ import annotations

import pytest

from tests.conftest import VALID_MESSAGE


def error_text(response) -> str:
    detail = response.json()["detail"]
    if isinstance(detail, list):
        return " ".join(item.get("msg", "") for item in detail)
    return str(detail)


async def test_valid_message_is_accepted(harness):
    response = await harness.client.post("/posting", json={"message": VALID_MESSAGE})

    assert response.status_code == 200
    assert len(response.json()["results"]) == 6


async def test_message_of_exactly_200_characters_is_accepted(harness):
    base = "Grow your online visibility today: https://example.com"
    message = base + "x" * (200 - len(base))
    assert len(message) == 200

    response = await harness.client.post("/posting", json={"message": message})
    assert response.status_code == 200


async def test_message_longer_than_200_characters_is_rejected(harness):
    message = "Grow your online visibility: https://example.com " + "x" * 200

    response = await harness.client.post("/posting", json={"message": message})

    assert response.status_code == 422
    assert "200 characters or fewer" in error_text(response)


async def test_missing_link_is_rejected(harness):
    response = await harness.client.post(
        "/posting", json={"message": "Check out our latest business platform."}
    )

    assert response.status_code == 422
    assert "exactly one call-to-action link" in error_text(response)


async def test_two_links_are_rejected(harness):
    message = "Two links here https://example.com and https://example.org"

    response = await harness.client.post("/posting", json={"message": message})

    assert response.status_code == 422
    assert "found 2" in error_text(response)


async def test_link_without_scheme_is_rejected_with_hint(harness):
    response = await harness.client.post(
        "/posting", json={"message": "Grow your visibility on example.com today"}
    )

    assert response.status_code == 422
    assert "http:// or https://" in error_text(response)


async def test_malformed_link_is_rejected(harness):
    response = await harness.client.post(
        "/posting", json={"message": "Grow your visibility on https:// today"}
    )

    assert response.status_code == 422
    assert "not a valid URL" in error_text(response)


async def test_unsupported_scheme_is_not_treated_as_a_link(harness):
    response = await harness.client.post(
        "/posting", json={"message": "Grow your visibility: ftp://example.com/file"}
    )

    assert response.status_code == 422


async def test_blank_message_is_rejected(harness):
    response = await harness.client.post("/posting", json={"message": "   "})

    assert response.status_code == 422


async def test_missing_message_field_is_rejected(harness):
    response = await harness.client.post("/posting", json={})

    assert response.status_code == 422


async def test_unknown_field_is_rejected(harness):
    response = await harness.client.post(
        "/posting", json={"message": VALID_MESSAGE, "platforms": ["bluesky"]}
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "link",
    [
        "https://example.com/path?utm_source=api#top",
        "http://sub.example.co.uk/a/b",
        "https://example.com:8443/landing",
    ],
)
async def test_link_variants_are_accepted(harness, link):
    response = await harness.client.post(
        "/posting", json={"message": f"Grow your visibility {link}"}
    )

    assert response.status_code == 200


async def test_trailing_punctuation_is_not_part_of_the_link(harness):
    response = await harness.client.post(
        "/posting", json={"message": "Grow your visibility https://example.com."}
    )

    assert response.status_code == 200
