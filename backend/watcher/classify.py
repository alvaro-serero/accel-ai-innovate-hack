"""Internship tagging, city normalisation and change keys. Owner: Leo.

All pure functions, regex only (no LLM): same input, same output.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


# ---------- internships ----------

# "early stage startup" is not an internship.
_NOT_AN_INTERNSHIP_RE = re.compile(r"\b(?:early|late|seed|growth|later|multi|next)[\s-]+stages?\b", re.I)
_INTERNSHIP_RE = re.compile(
    r"(?<!\w)(?:"
    r"interns?|internships?|"
    r"stages?|stagiaires?|"
    r"trainees?|traineeships?|"
    r"working[\s-]+students?|werkstudent(?:in)?|"
    r"fin[\s-]+d['\u2019]\s*etudes?"
    r")(?!\w)",
    re.I,
)


def is_internship(title: str | None, employment_type: str | None = None) -> bool:
    for field in (title, employment_type):
        if not field:
            continue
        text = _NOT_AN_INTERNSHIP_RE.sub(" ", strip_accents(field))
        if _INTERNSHIP_RE.search(text):
            return True
    return False


# ---------- cities ----------

_SEP = r"[\s-]+"

# Order matters: the first matching entry wins, so Paris comes first and Remote last.
CITY_MAP: list[tuple[str, list[str]]] = [
    (
        "Paris",
        [
            "paris", f"ile{_SEP}de{_SEP}france", "idf", f"la{_SEP}defense",
            f"boulogne{_SEP}billancourt", f"issy{_SEP}les{_SEP}moulineaux", f"levallois{_SEP}perret",
            f"neuilly{_SEP}sur{_SEP}seine", "puteaux", "courbevoie", "nanterre", f"saint{_SEP}ouen",
            f"saint{_SEP}denis", "montrouge", "clichy", "saclay", "palaiseau", "massy",
            f"rueil{_SEP}malmaison", "vincennes", "montreuil", f"ivry{_SEP}sur{_SEP}seine",
            "velizy", "versailles", "guyancourt", "malakoff", "gentilly", "pantin", "suresnes",
            f"saint{_SEP}cloud", "meudon", "sevres", "chatillon",
        ],
    ),
    ("Lyon", ["lyon", "villeurbanne"]),
    ("Marseille", ["marseille", f"aix{_SEP}en{_SEP}provence"]),
    ("Toulouse", ["toulouse"]),
    ("Bordeaux", ["bordeaux"]),
    ("Lille", ["lille"]),
    ("Nantes", ["nantes"]),
    ("Nice", ["nice", f"sophia{_SEP}antipolis", "valbonne"]),
    ("Grenoble", ["grenoble"]),
    ("Rennes", ["rennes"]),
    ("Montpellier", ["montpellier"]),
    ("Strasbourg", ["strasbourg"]),
    ("London", ["london", "londres"]),
    ("Dublin", ["dublin"]),
    ("Berlin", ["berlin"]),
    ("Munich", ["munich", "munchen", "muenchen"]),
    ("Hamburg", ["hamburg"]),
    ("Amsterdam", ["amsterdam"]),
    ("Brussels", ["brussels", "bruxelles"]),
    ("Luxembourg", ["luxembourg"]),
    ("Madrid", ["madrid"]),
    ("Barcelona", ["barcelona", "barcelone"]),
    ("Lisbon", ["lisbon", "lisboa", "lisbonne"]),
    ("Milan", ["milan", "milano"]),
    ("Zurich", ["zurich"]),
    ("Geneva", ["geneva", "geneve"]),
    ("Stockholm", ["stockholm"]),
    ("Copenhagen", ["copenhagen"]),
    ("Warsaw", ["warsaw", "warszawa"]),
    ("Tel Aviv", [f"tel{_SEP}aviv"]),
    ("New York", [f"new{_SEP}york", "nyc"]),
    ("San Francisco", [f"san{_SEP}francisco", f"bay{_SEP}area"]),
    ("Boston", ["boston"]),
    ("Seattle", ["seattle"]),
    ("Toronto", ["toronto"]),
    ("Montreal", ["montreal"]),
    ("Singapore", ["singapore"]),
    ("Remote", ["remote", "teletravail", f"full{_SEP}remote", f"work{_SEP}from{_SEP}home"]),
]

_CITY_RES = [
    (label, re.compile(r"(?<![a-z0-9])(?:" + "|".join(alts) + r")(?![a-z0-9])")) for label, alts in CITY_MAP
]
_REMOTE_RE = re.compile(r"(?<![a-z0-9])(?:remote|teletravail|work[\s-]+from[\s-]+home)(?![a-z0-9])")


def _norm_location(location: str | None) -> str:
    return strip_accents(location or "").lower()


def normalise_city(location: str | None) -> str | None:
    text = _norm_location(location)
    if not text.strip():
        return None
    for label, regex in _CITY_RES:
        if regex.search(text):
            return label
    return None


def mentions_remote(location: str | None) -> bool:
    return bool(_REMOTE_RE.search(_norm_location(location)))


def classify_posting(posting: dict) -> dict:
    """-> {is_internship, city, remote} for a normalised posting."""
    return {
        "is_internship": is_internship(posting.get("title"), posting.get("employment_type")),
        "city": normalise_city(posting.get("location")),
        # remote if the ATS says so or the location text says so
        "remote": bool(posting.get("remote")) or mentions_remote(posting.get("location")),
    }


# ---------- change and repost keys ----------


def content_hash(title: str | None, location: str | None, description: str | None) -> str:
    """sha1 of title, location, description. The unit separator keeps 'ab'+'c' != 'a'+'bc'."""
    payload = "\x1f".join(v or "" for v in (title, location, description))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


_PUNCT_RE = re.compile(r"[^\w\s]|_")


def normalise_title(title: str | None) -> str:
    """'Stagiaire Données – Paris (H/F)' -> 'stagiaire donnees paris hf'."""
    text = strip_accents(title or "").lower()
    text = _PUNCT_RE.sub("", text)
    return " ".join(text.split())
