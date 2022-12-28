#! /usr/bin/env python
"""Prescreen based on CLI"""
from __future__ import annotations

import typing
from dataclasses import dataclass

import zope.interface
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.record
import colrev.ui_cli.cli_colors as colors

if typing.TYPE_CHECKING:
    import colrev.ops.prescreen.Prescreen

# pylint: disable=too-few-public-methods


@zope.interface.implementer(
    colrev.env.package_manager.PrescreenPackageEndpointInterface
)
@dataclass
class CoLRevCLIPrescreen(JsonSchemaMixin):

    """CLI-based prescreen"""

    settings_class = colrev.env.package_manager.DefaultSettings

    def __init__(
        self,
        *,
        prescreen_operation: colrev.ops.prescreen.Prescreen,  # pylint: disable=unused-argument
        settings: dict,
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)

    def __fun_cli_prescreen(
        self,
        *,
        prescreen_operation: colrev.ops.prescreen.Prescreen,
        prescreen_data: dict,
        split: list,
        stat_len: int,
        padding: int,
    ) -> bool:

        if "" == prescreen_operation.review_manager.settings.prescreen.explanation:
            prescreen_operation.review_manager.settings.prescreen.explanation = input(
                f"\n{colors.ORANGE}Provide a short explanation of the prescreen{colors.END} "
                "(which papers should be included?):"
            )
            prescreen_operation.review_manager.save_settings()
        else:
            print("\nIn the prescreen, the following process is followed:\n")
            print(
                "   "
                + prescreen_operation.review_manager.settings.prescreen.explanation
            )
            print()

        prescreen_operation.review_manager.logger.debug("Start prescreen")

        if 0 == stat_len:
            prescreen_operation.review_manager.logger.info("No records to prescreen")

        i, quit_pressed = 0, False
        for record_dict in prescreen_data["items"]:
            if len(split) > 0:
                if record_dict["ID"] not in split:
                    continue

            prescreen_record = colrev.record.PrescreenRecord(data=record_dict)

            print("\n\n")
            print(prescreen_record)

            ret, inclusion_decision_str = "NA", "NA"
            i += 1

            while ret not in ["y", "n", "s", "q"]:
                ret = input(
                    f"({i}/{stat_len}) Include this record "
                    "[enter y,n,q,s for yes,no,quit,skip to decide later]? "
                )
                if "q" == ret:
                    quit_pressed = True
                elif "s" == ret:
                    continue
                else:
                    inclusion_decision_str = ret.replace("y", "yes").replace("n", "no")

            if quit_pressed:
                prescreen_operation.review_manager.logger.info("Stop prescreen")
                break

            if "s" == ret:
                continue

            inclusion_decision = "yes" == inclusion_decision_str
            prescreen_record.prescreen(
                review_manager=prescreen_operation.review_manager,
                prescreen_inclusion=inclusion_decision,
                PAD=padding,
            )

        return i == stat_len

    def run_prescreen(
        self,
        prescreen_operation: colrev.ops.prescreen.Prescreen,
        records: dict,
        split: list,
    ) -> dict:
        """Prescreen records based on a cli"""

        if not split:
            split = []

        prescreen_data = prescreen_operation.get_data()
        stat_len = len(split) if len(split) > 0 else prescreen_data["nr_tasks"]
        padding = prescreen_data["PAD"]

        completed = self.__fun_cli_prescreen(
            prescreen_operation=prescreen_operation,
            prescreen_data=prescreen_data,
            split=split,
            stat_len=stat_len,
            padding=padding,
        )

        # records = prescreen_operation.review_manager.dataset.load_records_dict()
        # prescreen_operation.review_manager.dataset.save_records_dict(records=records)
        prescreen_operation.review_manager.dataset.add_record_changes()

        if not completed:
            if "y" != input("Create commit (y/n)?"):
                return records

        prescreen_operation.review_manager.create_commit(
            msg="Pre-screening (manual)", manual_author=True, saved_args=None
        )
        return records


if __name__ == "__main__":
    pass
