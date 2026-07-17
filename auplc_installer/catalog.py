# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Course catalog and team-mapping data.

Single source of truth for the courses installed alongside the Hub. Mirrors
the bash COURSE_CATALOG / COURSE_PRESET_* / BASE_TEAM_MAPPING tables so the
overlay output is byte-for-byte the same.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Course catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Course:
    """A single course entry.

    ``key`` matches keys in runtime/values.yaml under
    custom.resources.{images,requirements,metadata} and is the string
    referenced by custom.teams.mapping.

    ``image_basename`` is the image name (without registry/tag) used by
    pull_custom_images / pack_save_custom_images_*.

    ``gpu_required`` decides image-tag style:
      * 1 → tagged ``:<IMAGE_TAG>-<gpu_target>`` (gfx-specific build)
      * 0 → tagged ``:<IMAGE_TAG>`` (plain build)

    ``make_target`` is the target name in dockerfiles/Makefile.
    """

    key: str
    image_basename: str
    gpu_required: bool
    make_target: str
    display_name: str


COURSE_CATALOG: tuple[Course, ...] = (
    Course("cpu", "auplc-default", False, "base-cpu", "Base CPU (Python Base Environment)"),
    Course("gpu", "auplc-base", True, "base-rocm", "Base GPU (GPU Base Environment)"),
    Course("code-cpu", "auplc-code-cpu", False, "code-cpu", "VSCode Server CPU Environment"),
    Course("code-gpu", "auplc-code-gpu", True, "code-gpu", "VSCode Server GPU Environment"),
    Course("Course-CV", "auplc-cv", True, "cv", "Computer Vision Course"),
    Course("Course-DL", "auplc-dl", True, "dl", "Deep Learning Course"),
    Course("Course-LLM", "auplc-llm", True, "llm", "Large Language Model Course"),
    Course("Course-PhySim", "auplc-physim", True, "physim", "Physical Simulation Course"),
)

COURSE_KEYS_ALL: tuple[str, ...] = tuple(c.key for c in COURSE_CATALOG)
COURSE_BY_KEY: dict[str, Course] = {c.key: c for c in COURSE_CATALOG}

COURSE_PRESET_BASIC: tuple[str, ...] = ("cpu", "gpu", "code-cpu", "code-gpu")
COURSE_PRESET_ALL: tuple[str, ...] = COURSE_KEYS_ALL


# Sentinel meaning "user explicitly picked nothing" (Hub only). Distinct from
# the empty selection, which means "use default = all courses" (back-compat
# with current CLI behaviour).
NONE_SENTINEL = "__none__"


# Always-built infrastructure image (Hub itself). Plain-tagged.
HUB_IMAGE_NAME = "auplc-hub"


# ---------------------------------------------------------------------------
# Base team→course mapping  (mirrors runtime/values.yaml custom.teams.mapping)
# ---------------------------------------------------------------------------
#
# When SELECTED_COURSES is non-empty the overlay rewrites each team's list
# as the intersection with the selection so unselected courses become
# invisible in the spawn UI.


BASE_TEAM_MAPPING: dict[str, list[str]] = {
    "cpu": ["cpu", "code-cpu"],
    "gpu": ["code-gpu", "Course-CV", "Course-DL", "Course-LLM", "Course-PhySim"],
    "official": [
        "cpu",
        "gpu",
        "code-cpu",
        "code-gpu",
        "Course-CV",
        "Course-DL",
        "Course-LLM",
        "Course-PhySim",
    ],
    "AUP": ["Course-CV", "Course-DL", "Course-LLM", "Course-PhySim"],
    "native-users": [
        "code-cpu",
        "code-gpu",
        "Course-CV",
        "Course-DL",
        "Course-LLM",
        "Course-PhySim",
        "cpu",
        "gpu",
    ],
    "github-users": [
        "cpu",
        "gpu",
        "code-cpu",
        "code-gpu",
        "Course-CV",
        "Course-DL",
        "Course-LLM",
        "Course-PhySim",
    ],
}


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


@dataclass
class CourseSelection:
    """User-selected courses.

    ``picks`` empty list means "use default = all courses" (back-compat).
    ``picks == [NONE_SENTINEL]`` means "Hub only, no courses". Else the
    list is the explicit subset the user picked.
    """

    picks: list[str]

    @classmethod
    def default(cls) -> CourseSelection:
        return cls(picks=[])

    def is_default(self) -> bool:
        return len(self.picks) == 0

    def is_none(self) -> bool:
        return self.picks == [NONE_SENTINEL]

    def effective_keys(self) -> list[str]:
        """Course keys to operate on. Empty selection → all keys (back-compat)."""
        if self.is_default():
            return list(COURSE_KEYS_ALL)
        if self.is_none():
            return []
        return list(self.picks)

    def is_selected(self, key: str) -> bool:
        if self.is_default():
            return True
        if self.is_none():
            return False
        return key in self.picks

    def description(self) -> str:
        """Human-readable summary used in overlay comments and TUI screens."""
        if self.is_default():
            return "all (default)"
        if self.is_none():
            return "none"
        return ", ".join(self.picks)

    def gpu_image_basenames(self) -> list[str]:
        """Image basenames for selected GPU-tagged courses."""
        return [
            COURSE_BY_KEY[k].image_basename
            for k in self.effective_keys()
            if k in COURSE_BY_KEY and COURSE_BY_KEY[k].gpu_required
        ]

    def plain_image_basenames(self) -> list[str]:
        """Image basenames for selected plain-tagged courses (excludes ``auplc-hub``)."""
        return [
            COURSE_BY_KEY[k].image_basename
            for k in self.effective_keys()
            if k in COURSE_BY_KEY and not COURSE_BY_KEY[k].gpu_required
        ]

    def make_targets(self) -> list[str]:
        """Makefile targets for selected courses."""
        return [COURSE_BY_KEY[k].make_target for k in self.effective_keys() if k in COURSE_BY_KEY]


def parse_selection_spec(spec: str) -> CourseSelection:
    """Translate a CLI / env-var string into a :class:`CourseSelection`.

    Accepts ``""`` (default = all), ``"all"``, ``"basic"``, ``"none"``,
    or a comma-separated list of catalog keys.
    """
    from auplc_installer.util import InstallerError

    if not spec:
        return CourseSelection.default()
    spec = spec.strip()
    low = spec.lower()
    if low == "all":
        return CourseSelection(picks=list(COURSE_PRESET_ALL))
    if low == "basic":
        return CourseSelection(picks=list(COURSE_PRESET_BASIC))
    if low == "none":
        return CourseSelection(picks=[NONE_SENTINEL])

    out: list[str] = []
    for raw in spec.split(","):
        key = raw.strip()
        if not key:
            continue
        if key not in COURSE_BY_KEY:
            valid = " ".join(COURSE_KEYS_ALL)
            raise InstallerError(f"unknown course key '{key}'.\nValid keys: {valid}")
        out.append(key)
    return CourseSelection(picks=out)
