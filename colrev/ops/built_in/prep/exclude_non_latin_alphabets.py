#! /usr/bin/env python
"""Exclude records with non-latin alphabets as a prep operation"""
from __future__ import annotations

from dataclasses import dataclass

import zope.interface
from alphabet_detector import AlphabetDetector
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.ops.search_sources
import colrev.record
from colrev.constants import Fields

# pylint: disable=duplicate-code


# pylint: disable=too-few-public-methods


@zope.interface.implementer(colrev.env.package_manager.PrepPackageEndpointInterface)
@dataclass
class ExcludeNonLatinAlphabetsPrep(JsonSchemaMixin):
    """Prepares records by excluding ones that have a non-latin alphabet
    (in the title, author, journal, or booktitle field)"""

    settings_class = colrev.env.package_manager.DefaultSettings
    ci_supported: bool = True

    source_correction_hint = "check with the developer"
    always_apply_changes = True
    alphabet_detector = AlphabetDetector()

    def __init__(
        self,
        *,
        prep_operation: colrev.ops.prep.Prep,
        settings: dict,
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)
        self.prep_operation = prep_operation

    def _mostly_latin_alphabet(self, str_to_check: str) -> bool:
        assert len(str_to_check) != 0
        nr_latin = 0
        for character in str_to_check:
            if self.alphabet_detector.only_alphabet_chars(character, "LATIN"):
                nr_latin += 1
        return nr_latin / len(str_to_check) > 0.75

    def prepare(
        self,
        record: colrev.record_prep.PrepRecord,
    ) -> colrev.record.Record:
        """Prepare the records by excluding records whose metadata is not in Latin alphabet"""

        if self.prep_operation.polish:
            return record

        # TB:D join or check independently?
        str_to_check = " ".join(
            [
                record.data.get(Fields.TITLE, ""),
            ]
        )

        if str_to_check and not self._mostly_latin_alphabet(str_to_check):
            record.prescreen_exclude(reason="non_latin_alphabet")

        return record
