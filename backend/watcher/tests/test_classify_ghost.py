from datetime import datetime, timedelta, timezone

import pytest

from backend.watcher.classify import (
    classify_posting,
    content_hash,
    is_internship,
    normalise_city,
    normalise_title,
)
from backend.watcher.discover import extract_board, slug_variants
from backend.watcher.ghost import ghost_score

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


# ---------- internships ----------

@pytest.mark.parametrize("title", [
    "ML Engineer Intern", "INTERNSHIP - Data", "Stage Data Scientist (H/F)", "Stagiaire Marketing",
    "Graduate Trainee", "Working Student Backend", "Stage de fin d'études - IA", "Stage de fin d'etudes",
    "Stage de fin d\u2019études", "(Stage) Product", "Stage/Internship", "Intern-Data",
])
def test_internship_titles(title):
    assert is_internship(title)


@pytest.mark.parametrize("title", [
    "Internal Tools Engineer", "International Sales Manager", "Internet Ops", "Backstage Engineer",
    "Engineer at an early stage startup", "Senior Data Scientist", "", None,
])
def test_not_internship_titles(title):
    assert not is_internship(title)


def test_internship_from_employment_type():
    assert is_internship("Software Engineer", "Intern")
    assert is_internship(None, "Internship")
    assert not is_internship("Software Engineer", "FullTime")


# ---------- cities ----------

@pytest.mark.parametrize("location,city", [
    ("Paris, France", "Paris"),
    ("PARIS", "Paris"),
    ("Île-de-France", "Paris"),
    ("Ile de France", "Paris"),
    ("La Défense", "Paris"),
    ("Boulogne-Billancourt, FR", "Paris"),
    ("London, UK", "London"),
    ("London or Paris", "Paris"),  # table order wins: Paris is first
    ("Remote - Paris", "Paris"),
    ("Remote", "Remote"),
    ("Parisian Road, Singapore", "Singapore"),
    ("Kraków", None),
    ("", None),
    (None, None),
])
def test_city_map(location, city):
    assert normalise_city(location) == city


def test_classify_posting_remote():
    base = {"title": "Intern", "employment_type": None, "location": "Remote, France", "remote": None}
    assert classify_posting(base) == {"is_internship": True, "city": "Remote", "remote": True}
    assert classify_posting({**base, "location": "Paris", "remote": True})["remote"] is True
    assert classify_posting({**base, "location": "Paris", "remote": False})["remote"] is False


# ---------- change keys ----------

def test_content_hash():
    h = content_hash("Intern", "Paris", "desc")
    assert len(h) == 40 and h == content_hash("Intern", "Paris", "desc")
    assert h != content_hash("Intern", "Paris", "desc 2")
    assert content_hash("Intern", None, "d") == content_hash("Intern", "", "d")
    assert content_hash("ab", "c", None) != content_hash("a", "bc", None)


def test_normalise_title():
    assert normalise_title("ML Engineer Intern ") == normalise_title("ml engineer  intern") == "ml engineer intern"
    assert normalise_title("Stagiaire Données – Paris (H/F)") == "stagiaire donnees paris hf"
    assert normalise_title(normalise_title("Stagiaire Données")) == normalise_title("Stagiaire Données")
    assert normalise_title(None) == "" and normalise_title(" -- ") == ""


# ---------- ghost ----------

def score(**kw):
    args = {"title": "ML Intern", "published_at": NOW, "first_seen_at": NOW,
            "source_updated_at": None, "repost_count": 0, "now": NOW}
    args.update(kw)
    return ghost_score(**args)


def days_ago(n):
    return NOW - timedelta(days=n)


def test_ghost_fresh():
    assert score() == (0, [])


@pytest.mark.parametrize("age,expected", [(60, 0), (61, 0.4), (120, 0.4), (121, 0.6)])
def test_ghost_age_boundaries(age, expected):
    s, reasons = score(published_at=days_ago(age))
    assert s == expected
    assert len(reasons) == (1 if expected else 0)
    if expected:
        assert str(age) in reasons[0]


def test_ghost_age_falls_back_to_first_seen():
    assert score(published_at=None, first_seen_at=days_ago(70))[0] == 0.4


@pytest.mark.parametrize("kw,expected", [
    ({"repost_count": 2}, 0.3),
    ({"title": "Candidature spontanée"}, 0.5),
    ({"title": "Talent Pool - Engineering"}, 0.5),
    ({"source_updated_at": days_ago(91)}, 0.2),
    ({"source_updated_at": days_ago(90)}, 0),
])
def test_ghost_single_rules(kw, expected):
    s, reasons = score(**kw)
    assert s == expected
    assert len(reasons) == (1 if expected else 0)


def test_ghost_sum_and_cap():
    assert score(published_at=days_ago(90), repost_count=1)[0] == 0.7
    s, reasons = score(published_at=days_ago(200), title="Spontaneous application", repost_count=1,
                       source_updated_at=days_ago(200))
    assert s == 1.0 and len(reasons) == 4


def test_ghost_future_dates():
    assert score(published_at=NOW + timedelta(days=5), source_updated_at=NOW + timedelta(days=5)) == (0, [])


# ---------- discovery helpers ----------

@pytest.mark.parametrize("url,board", [
    ("https://boards.greenhouse.io/datadog/jobs/123", ("greenhouse", "datadog")),
    ("https://job-boards.greenhouse.io/Datadog", ("greenhouse", "datadog")),
    ("https://boards.greenhouse.io/embed/job_board?for=algolia", ("greenhouse", "algolia")),
    ("https://jobs.lever.co/mistral/abc-123?lever-source=x", ("lever", "mistral")),
    ("https://jobs.eu.lever.co/qonto/abc", ("lever", "qonto")),
    ("https://jobs.ashbyhq.com/photoroom/085eaa32", ("ashby", "photoroom")),
    ("https://www.welcometothejungle.com/fr/companies/x", None),
    ("https://jobs.lever.co/", None),
    ("not a url", None),
])
def test_extract_board(url, board):
    assert extract_board(url) == board


def test_slug_variants():
    assert slug_variants("Mistral AI") == ["mistralai", "mistral-ai", "mistral"]
    assert slug_variants("Datadog") == ["datadog"]
    assert slug_variants("Crème de la Crème") == ["cremedelacreme", "creme-de-la-creme"]
    assert slug_variants("") == []
