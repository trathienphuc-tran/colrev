#! /usr/bin/env python
"""SearchSource: Springer Link"""
from __future__ import annotations

import re
import typing
from dataclasses import dataclass
from pathlib import Path

import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.search
import colrev.record

# pylint: disable=unused-argument
# pylint: disable=duplicate-code

# Note : API requires registration
# https://dev.springernature.com/


@zope.interface.implementer(
    colrev.env.package_manager.SearchSourcePackageEndpointInterface
)
@dataclass
class SpringerLinkSearchSource(JsonSchemaMixin):
    """SearchSource for Springer Link"""

    settings_class = colrev.env.package_manager.DefaultSourceSettings
    source_identifier = "{{url}}"
    search_type = colrev.settings.SearchType.DB
    heuristic_status = colrev.env.package_manager.SearchSourceHeuristicStatus.supported
    short_name = "Springer Link"
    link = "https://link.springer.com/"

    def __init__(
        self, *, source_operation: colrev.operation.CheckOperation, settings: dict
    ) -> None:
        self.search_source = from_dict(data_class=self.settings_class, data=settings)

    def validate_source(
        self,
        search_operation: colrev.ops.search.Search,
        source: colrev.settings.SearchSource,
    ) -> None:
        """Validate the SearchSource (parameters etc.)"""

        search_operation.review_manager.logger.debug(
            f"Validate SearchSource {source.filename}"
        )

        if source.source_identifier != self.source_identifier:
            raise colrev_exceptions.InvalidQueryException(
                f"Invalid source_identifier: {source.source_identifier} "
                f"(should be {self.source_identifier})"
            )

        if "query_file" not in source.search_parameters:
            raise colrev_exceptions.InvalidQueryException(
                f"Source missing query_file search_parameter ({source.filename})"
            )

        if not Path(source.search_parameters["query_file"]).is_file():
            raise colrev_exceptions.InvalidQueryException(
                f"File does not exist: query_file {source.search_parameters['query_file']} "
                f"for ({source.filename})"
            )

        search_operation.review_manager.logger.debug(
            f"SearchSource {source.filename} validated"
        )

    @classmethod
    def heuristic(cls, filename: Path, data: str) -> dict:
        """Source heuristic for Springer Link"""

        result = {"confidence": 0.1}

        if filename.suffix == ".csv":
            if data.count("http://link.springer.com") == data.count("\n"):
                result["confidence"] = 1.0
                return result

        # Note : no features in bib file for identification

        return result

    def load_fixes(
        self,
        load_operation: colrev.ops.load.Load,
        source: colrev.settings.SearchSource,
        records: typing.Dict,
    ) -> dict:
        """Load fixes for Springer Link"""

        # pylint: disable=too-many-branches

        for record in records.values():
            if "item_title" in record:
                record["title"] = record["item_title"]
                del record["item_title"]

            if "content_type" in record:
                if "Article" == record["content_type"]:
                    record["ENTRYTYPE"] = "article"
                    if "publication_title" in record:
                        record["journal"] = record["publication_title"]
                        del record["publication_title"]

                if "Book" == record["content_type"]:
                    record["ENTRYTYPE"] = "book"
                    if "publication_title" in record:
                        record["series"] = record["publication_title"]
                        del record["publication_title"]

                if "Chapter" == record["content_type"]:
                    record["ENTRYTYPE"] = "inbook"
                    record["chapter"] = record["title"]
                    if "publication_title" in record:
                        record["title"] = record["publication_title"]
                        del record["publication_title"]

                del record["content_type"]

            if "item_doi" in record:
                record["doi"] = record["item_doi"]
                del record["item_doi"]
            if "journal_volume" in record:
                record["volume"] = record["journal_volume"]
                del record["journal_volume"]
            if "journal_issue" in record:
                record["number"] = record["journal_issue"]
                del record["journal_issue"]

            # Fix authors
            if "author" in record:
                # a-bd-z: do not match McDonald
                record["author"] = re.sub(
                    r"([a-bd-z]{1})([A-Z]{1})", r"\g<1> and \g<2>", record["author"]
                )

        return records

    def prepare(
        self, record: colrev.record.Record, source: colrev.settings.SearchSource
    ) -> colrev.record.Record:
        """Source-specific preparation for Springer Link"""

        return record


if __name__ == "__main__":
    pass
