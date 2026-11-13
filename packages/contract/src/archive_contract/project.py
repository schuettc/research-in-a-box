"""The project record, `project.json`, that packages name by id."""

from pydantic import Field as PydanticField

from archive_contract._base import ArchiveModel


class Person(ArchiveModel):
    name: str
    roles: list[str] = PydanticField(default_factory=list)
    email: str | None = None
    orcid: str | None = None
    organization: str | None = None


class Link(ArchiveModel):
    url: str
    title: str | None = None


class Project(ArchiveModel):
    """A monitoring program, a grant or a long-term study.

    A package names its project with `archive:project: <id>` and never copies its text.
    """

    id: str
    title: str
    abstract: str | None = None
    people: list[Person] = PydanticField(default_factory=list)
    links: list[Link] = PydanticField(default_factory=list)
