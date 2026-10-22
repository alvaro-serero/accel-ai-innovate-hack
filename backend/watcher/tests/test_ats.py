"""Parsers only: sample payloads shaped like the real API responses, no network."""
from datetime import datetime, timezone

import pytest

from backend.watcher.ats import POSTING_KEYS, html_to_text, parse_ashby, parse_greenhouse, parse_lever

UTC = timezone.utc


def test_greenhouse_maps_every_field():
    payload = {
        "jobs": [
            {
                "id": 8257324,
                "title": "Data Science Intern",
                "location": {"name": "Paris, France"},
                "absolute_url": "https://careers.example.com/detail/8257324",
                "updated_at": "2026-10-06T10:42:08-04:00",
                "first_published": "2026-10-01T09:00:00-04:00",
                "content": "&lt;h2&gt;About&lt;/h2&gt;&lt;p&gt;Build &amp;amp; ship&amp;nbsp;models&lt;/p&gt;",
                "metadata": [
                    {"name": "Cost Center", "value": "R&D"},
                    {"name": "Time Type", "value": "Intern"},
                ],
            }
        ],
        "meta": {"total": 1},
    }
    [p] = parse_greenhouse(payload)
    assert set(p) == set(POSTING_KEYS)
    assert p == {
        "ats_job_id": "8257324",
        "title": "Data Science Intern",
        "location": "Paris, France",
        "remote": False,
        "employment_type": "Intern",
        "url": "https://careers.example.com/detail/8257324",
        "description": "About Build & ship models",  # &nbsp; collapsed like any whitespace
        "published_at": datetime(2026, 10, 1, 13, 0, tzinfo=UTC),
        "source_updated_at": datetime(2026, 10, 6, 14, 42, 8, tzinfo=UTC),
    }


def test_greenhouse_missing_fields_and_skips():
    payload = {"jobs": [{"id": 1, "title": "Engineer - Remote"}, {"id": 2}, {"title": "no id"}, "junk"]}
    [p] = parse_greenhouse(payload)
    assert p["ats_job_id"] == "1"
    assert p["location"] is None and p["published_at"] is None and p["description"] is None
    assert p["remote"] is False  # remote comes from the location only
    assert parse_greenhouse({"jobs": [{"id": 3, "title": "SWE", "location": {"name": "Remote, EU"}}]})[0]["remote"]
    assert parse_greenhouse({"jobs": []}) == []


def test_greenhouse_bad_shape():
    with pytest.raises(ValueError):
        parse_greenhouse([{"id": 1}])


def test_lever_maps_every_field():
    payload = [
        {
            "id": "a1b2",
            "text": "Stage - Machine Learning",
            "categories": {"location": "Paris", "commitment": "Internship", "allLocations": ["Paris", "Lyon"]},
            "hostedUrl": "https://jobs.lever.co/acme/a1b2",
            "createdAt": 1700000000000,
            "descriptionPlain": "Join us.",
            "lists": [{"text": "Requirements", "content": "<li>Python</li><li>PyTorch</li>"}],
            "additionalPlain": "Paris office.",
            "workplaceType": "hybrid",
        }
    ]
    [p] = parse_lever(payload)
    assert p == {
        "ats_job_id": "a1b2",
        "title": "Stage - Machine Learning",
        "location": "Paris; Lyon",
        "remote": False,
        "employment_type": "Internship",
        "url": "https://jobs.lever.co/acme/a1b2",
        "description": "Join us.\n\nRequirements Python PyTorch\n\nParis office.",
        "published_at": datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        "source_updated_at": None,
    }


def test_lever_missing_fields_and_skips():
    payload = [{"id": "x", "text": "SWE", "workplaceType": "remote", "createdAt": "yesterday"}, {"id": "y", "text": "  "}]
    [p] = parse_lever(payload)
    assert p["remote"] is True
    assert p["published_at"] is None and p["location"] is None and p["employment_type"] is None
    with pytest.raises(ValueError):
        parse_lever({"jobs": []})


def test_ashby_maps_every_field():
    payload = {
        "apiVersion": "1",
        "jobs": [
            {
                "id": "085eaa32",
                "title": "Software Engineer Intern",
                "employmentType": "Intern",
                "location": "Paris",
                "secondaryLocations": [{"location": "London"}],
                "publishedAt": "2026-07-12T12:57:19.845+00:00",
                "isListed": True,
                "isRemote": True,
                "workplaceType": "Hybrid",
                "jobUrl": "https://jobs.ashbyhq.com/acme/085eaa32",
                "descriptionPlain": "About us",
            },
            {"id": "hidden", "title": "Unlisted", "isListed": False},
        ],
    }
    [p] = parse_ashby(payload)
    assert p == {
        "ats_job_id": "085eaa32",
        "title": "Software Engineer Intern",
        "location": "Paris; London",
        "remote": False,  # workplaceType wins over isRemote
        "employment_type": "Intern",
        "url": "https://jobs.ashbyhq.com/acme/085eaa32",
        "description": "About us",
        "published_at": datetime(2026, 7, 12, 12, 57, 19, 845000, tzinfo=UTC),
        "source_updated_at": None,
    }


def test_ashby_missing_fields_and_skips():
    payload = {"jobs": [{"id": "1", "title": "PM", "isRemote": True, "descriptionHtml": "<p>Hi &amp; bye</p>"}, {"id": "2"}]}
    [p] = parse_ashby(payload)
    assert p["remote"] is True and p["description"] == "Hi & bye"
    assert p["published_at"] is None and p["location"] is None
    assert parse_ashby({"jobs": []}) == []


def test_html_to_text():
    assert html_to_text(None) is None
    assert html_to_text("&lt;p&gt;a&lt;/p&gt;\n\n&lt;p&gt;b&lt;/p&gt;") == "a b"
