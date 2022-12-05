#! /usr/bin/env python
"""SearchSource: directory containing PDF files (based on GROBID)"""
from __future__ import annotations

import re
import typing
from dataclasses import dataclass
from pathlib import Path

import zope.interface
from dacite import from_dict
from dataclasses_jsonschema import JsonSchemaMixin
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import resolve1
from pdfminer.pdfparser import PDFParser

import colrev.env.package_manager
import colrev.exceptions as colrev_exceptions
import colrev.ops.built_in.search_sources.pdf_backward_search as bws
import colrev.ops.built_in.search_sources.utils as connector_utils
import colrev.ops.search
import colrev.record
import colrev.ui_cli.cli_colors as colors

# pylint: disable=unused-argument
# pylint: disable=duplicate-code


@zope.interface.implementer(
    colrev.env.package_manager.SearchSourcePackageEndpointInterface
)
@dataclass
class PDFSearchSource(JsonSchemaMixin):
    """SearchSource for PDF directories (based on GROBID)"""

    # pylint: disable=too-many-instance-attributes

    settings_class = colrev.env.package_manager.DefaultSourceSettings
    source_identifier = "{{file}}"
    search_type = colrev.settings.SearchType.PDFS

    def __init__(
        self, *, source_operation: colrev.operation.CheckOperation, settings: dict
    ) -> None:

        self.search_source = from_dict(data_class=self.settings_class, data=settings)
        self.source_operation = source_operation
        self.pdf_preparation_operation = (
            source_operation.review_manager.get_pdf_prep_operation(
                notify_state_transition_operation=False
            )
        )

        self.pdfs_path = source_operation.review_manager.path / Path(
            self.search_source.search_parameters["scope"]["path"]
        )
        self.review_manager = source_operation.review_manager

        self.subdir_pattern: re.Pattern = re.compile("")
        self.r_subdir_pattern: re.Pattern = re.compile("")
        if "subdir_pattern" in self.search_source.search_parameters.get("scope", {}):
            self.subdir_pattern = self.search_source.search_parameters["scope"][
                "subdir_pattern"
            ]
            source_operation.review_manager.logger.info(
                f"Activate subdir_pattern: {self.subdir_pattern}"
            )
            if "year" == self.subdir_pattern:
                self.r_subdir_pattern = re.compile("([1-3][0-9]{3})")
            if "volume_number" == self.subdir_pattern:
                self.r_subdir_pattern = re.compile("([0-9]{1,3})(_|/)([0-9]{1,2})")
            if "volume" == self.subdir_pattern:
                self.r_subdir_pattern = re.compile("([0-9]{1,4})")

    def __update_if_pdf_renamed(
        self,
        *,
        search_operation: colrev.ops.search.Search,
        record_dict: dict,
        records: dict,
        search_source: Path,
    ) -> bool:
        updated = True
        not_updated = False

        c_rec_l = [
            r
            for r in records.values()
            if f"{search_source}/{record_dict['ID']}" in r["colrev_origin"]
        ]
        if len(c_rec_l) == 1:
            c_rec = c_rec_l.pop()
            if "colrev_pdf_id" in c_rec:
                cpid = c_rec["colrev_pdf_id"]
                pdf_fp = search_operation.review_manager.path / Path(
                    record_dict["file"]
                )
                pdf_path = pdf_fp.parents[0]
                potential_pdfs = pdf_path.glob("*.pdf")

                for potential_pdf in potential_pdfs:
                    cpid_potential_pdf = colrev.record.Record.get_colrev_pdf_id(
                        review_manager=search_operation.review_manager,
                        pdf_path=potential_pdf,
                    )

                    if cpid == cpid_potential_pdf:
                        record_dict["file"] = str(
                            potential_pdf.relative_to(
                                search_operation.review_manager.path
                            )
                        )
                        c_rec["file"] = str(
                            potential_pdf.relative_to(
                                search_operation.review_manager.path
                            )
                        )
                        return updated
        return not_updated

    def __remove_records_if_pdf_no_longer_exists(
        self, *, search_operation: colrev.ops.search.Search
    ) -> None:

        # search_operation.review_manager.logger.debug(
        #     "Checking for PDFs that no longer exist"
        # )

        if not self.search_source.filename.is_file():
            return

        with open(self.search_source.filename, encoding="utf8") as target_db:

            search_rd = search_operation.review_manager.dataset.load_records_dict(
                load_str=target_db.read()
            )

        records = {}
        if search_operation.review_manager.dataset.records_file.is_file():
            records = search_operation.review_manager.dataset.load_records_dict()

        to_remove: typing.List[str] = []
        files_removed = []
        for record_dict in search_rd.values():
            x_pdf_path = search_operation.review_manager.path / Path(
                record_dict["file"]
            )
            if not x_pdf_path.is_file():
                if records:
                    updated = self.__update_if_pdf_renamed(
                        search_operation=search_operation,
                        record_dict=record_dict,
                        records=records,
                        search_source=self.search_source.filename,
                    )
                    if updated:
                        continue
                to_remove.append(
                    f"{self.search_source.filename.name}/{record_dict['ID']}"
                )
                files_removed.append(record_dict["file"])

        search_rd = {
            x["ID"]: x
            for x in search_rd.values()
            if (search_operation.review_manager.path / Path(x["file"])).is_file()
        }

        if len(search_rd.values()) != 0:
            search_operation.review_manager.dataset.save_records_dict_to_file(
                records=search_rd, save_path=self.search_source.filename
            )

        if search_operation.review_manager.dataset.records_file.is_file():
            for record_dict in records.values():
                for origin_to_remove in to_remove:
                    if origin_to_remove in record_dict["colrev_origin"]:
                        record_dict["colrev_origin"].remove(origin_to_remove)
            if to_remove:
                search_operation.review_manager.logger.info(
                    f" {colors.RED}Removed {len(to_remove)} records "
                    f"(PDFs no longer available){colors.END}"
                )
                print(" " + "\n ".join(files_removed))
            records = {k: v for k, v in records.items() if v["colrev_origin"]}
            search_operation.review_manager.dataset.save_records_dict(records=records)
            search_operation.review_manager.dataset.add_record_changes()

    def __update_fields_based_on_pdf_dirs(
        self, *, record_dict: dict, params: dict
    ) -> dict:
        if not self.subdir_pattern:
            return record_dict

        if "journal" in params["scope"]:
            record_dict["journal"] = params["scope"]["journal"]
            record_dict["ENTRYTYPE"] = "article"

        if "conference" in params["scope"]:
            record_dict["booktitle"] = params["scope"]["conference"]
            record_dict["ENTRYTYPE"] = "inproceedings"

        if self.subdir_pattern:

            # Note : no file access here (just parsing the patterns)
            # no absolute paths needed
            partial_path = Path(record_dict["file"]).parents[0]

            if "year" == self.subdir_pattern:
                # Note: for year-patterns, we allow subfolders
                # (eg., conference tracks)
                match = self.r_subdir_pattern.search(str(partial_path))
                if match is not None:
                    year = match.group(1)
                    record_dict["year"] = year

            elif "volume_number" == self.subdir_pattern:
                match = self.r_subdir_pattern.search(str(partial_path))
                if match is not None:
                    volume = match.group(1)
                    number = match.group(3)
                    record_dict["volume"] = volume
                    record_dict["number"] = number
                else:
                    # sometimes, journals switch...
                    r_subdir_pattern = re.compile("([0-9]{1,3})")
                    match = r_subdir_pattern.search(str(partial_path))
                    if match is not None:
                        volume = match.group(1)
                        record_dict["volume"] = volume

            elif "volume" == self.subdir_pattern:
                match = self.r_subdir_pattern.search(str(partial_path))
                if match is not None:
                    volume = match.group(1)
                    record_dict["volume"] = volume

        return record_dict

    # curl -v --form input=@./profit.pdf localhost:8070/api/processHeaderDocument
    # curl -v --form input=@./thefile.pdf -H "Accept: application/x-bibtex"
    # -d "consolidateHeader=0" localhost:8070/api/processHeaderDocument
    def __get_record_from_pdf_grobid(
        self, *, search_operation: colrev.ops.search.Search, record_dict: dict
    ) -> dict:

        if colrev.record.RecordState.md_prepared == record_dict.get(
            "colrev_status", "NA"
        ):
            return record_dict

        pdf_path = search_operation.review_manager.path / Path(record_dict["file"])
        tei = search_operation.review_manager.get_tei(
            pdf_path=pdf_path,
        )

        extracted_record = tei.get_metadata()

        for key, val in extracted_record.items():
            if val:
                record_dict[key] = str(val)

        with open(pdf_path, "rb") as file:
            parser = PDFParser(file)
            doc = PDFDocument(parser)

            if record_dict.get("title", "NA") in ["NA", ""]:
                if "Title" in doc.info[0]:
                    try:
                        record_dict["title"] = doc.info[0]["Title"].decode("utf-8")
                    except UnicodeDecodeError:
                        pass
            if record_dict.get("author", "NA") in ["NA", ""]:
                if "Author" in doc.info[0]:
                    try:
                        pdf_md_author = doc.info[0]["Author"].decode("utf-8")
                        if (
                            "Mirko Janc" not in pdf_md_author
                            and "wendy" != pdf_md_author
                            and "yolanda" != pdf_md_author
                        ):
                            record_dict["author"] = pdf_md_author
                    except UnicodeDecodeError:
                        pass

            if "abstract" in record_dict:
                del record_dict["abstract"]
            if "keywords" in record_dict:
                del record_dict["keywords"]

            # to allow users to update/reindex with newer version:
            record_dict["grobid-version"] = (
                "lfoppiano/grobid:" + tei.get_grobid_version()
            )

            return record_dict

    def __index_pdf(
        self, *, search_operation: colrev.ops.search.Search, pdf_path: Path
    ) -> dict:

        search_operation.review_manager.report_logger.info(
            f" extract metadata from {pdf_path}"
        )
        search_operation.review_manager.logger.info(
            f" extract metadata from {pdf_path}"
        )

        record_dict: typing.Dict[str, typing.Any] = {
            "file": str(pdf_path),
            "ENTRYTYPE": "misc",
        }
        try:
            record_dict = self.__get_record_from_pdf_grobid(
                search_operation=search_operation, record_dict=record_dict
            )

            with open(pdf_path, "rb") as file:
                parser = PDFParser(file)
                document = PDFDocument(parser)
                pages_in_file = resolve1(document.catalog["Pages"])["Count"]
                if pages_in_file < 6:
                    record = colrev.record.Record(data=record_dict)
                    record.set_text_from_pdf(
                        project_path=search_operation.review_manager.path
                    )
                    record_dict = record.get_data()
                    if "text_from_pdf" in record_dict:
                        text: str = record_dict["text_from_pdf"]
                        if "bookreview" in text.replace(" ", "").lower():
                            record_dict["ENTRYTYPE"] = "misc"
                            record_dict["note"] = "Book review"
                        if "erratum" in text.replace(" ", "").lower():
                            record_dict["ENTRYTYPE"] = "misc"
                            record_dict["note"] = "Erratum"
                        if "correction" in text.replace(" ", "").lower():
                            record_dict["ENTRYTYPE"] = "misc"
                            record_dict["note"] = "Correction"
                        if "contents" in text.replace(" ", "").lower():
                            record_dict["ENTRYTYPE"] = "misc"
                            record_dict["note"] = "Contents"
                        if "withdrawal" in text.replace(" ", "").lower():
                            record_dict["ENTRYTYPE"] = "misc"
                            record_dict["note"] = "Withdrawal"
                        del record_dict["text_from_pdf"]
                    # else:
                    #     print(f'text extraction error in {record_dict["ID"]}')
                    if "pages_in_file" in record_dict:
                        del record_dict["pages_in_file"]

                record_dict = {k: v for k, v in record_dict.items() if v is not None}
                record_dict = {k: v for k, v in record_dict.items() if v != "NA"}

                # add details based on path
                record_dict = self.__update_fields_based_on_pdf_dirs(
                    record_dict=record_dict, params=self.search_source.search_parameters
                )

        except colrev_exceptions.TEIException:
            pass

        return record_dict

    def __is_broken_filepath(
        self,
        pdf_path: Path,
    ) -> bool:

        if ";" in str(pdf_path):
            self.review_manager.logger.error(
                f'skipping PDF with ";" in filepath: \n{pdf_path}'
            )
            return True

        if (
            "_ocr.pdf" == str(pdf_path)[-8:]
            or "_wo_cp.pdf" == str(pdf_path)[-10:]
            or "_wo_lp.pdf" == str(pdf_path)[-10:]
            or "_backup.pdf" == str(pdf_path)[-11:]
        ):

            self.review_manager.logger.info(
                f"Skipping PDF with _ocr.pdf/_wo_cp.pdf: {pdf_path}"
            )
            return True

        return False

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

        if "subdir_pattern" in source.search_parameters:
            if source.search_parameters["subdir_pattern"] != [
                "NA",
                "volume_number",
                "year",
                "volume",
            ]:
                raise colrev_exceptions.InvalidQueryException(
                    "subdir_pattern not in [NA, volume_number, year, volume]"
                )

        if "sub_dir_pattern" in source.search_parameters:
            raise colrev_exceptions.InvalidQueryException(
                "sub_dir_pattern: deprecated. use subdir_pattern"
            )

        if "scope" not in source.search_parameters:
            raise colrev_exceptions.InvalidQueryException(
                "scope required in search_parameters"
            )
        if "path" not in source.search_parameters["scope"]:
            raise colrev_exceptions.InvalidQueryException(
                "path required in search_parameters/scope"
            )
        search_operation.review_manager.logger.debug(
            f"SearchSource {source.filename} validated"
        )

    def __add_md_string(self, *, record_dict: dict) -> dict:

        md_copy = record_dict.copy()
        try:
            fsize = str(
                (self.review_manager.path / Path(record_dict["file"])).stat().st_size
            )
        except FileNotFoundError:
            fsize = "NOT_FOUND"
        for key in ["ID", "grobid-version", "file"]:
            if key in md_copy:
                md_copy.pop(key)
        md_string = ",".join([f"{k}:{v}" for k, v in md_copy.items()])
        record_dict["md_string"] = str(fsize) + md_string
        return record_dict

    def run_search(
        self, search_operation: colrev.ops.search.Search, update_only: bool
    ) -> None:
        """Run a search of a PDF directory (based on GROBID)"""

        # pylint: disable=too-many-locals

        # Removing records/origins for which PDFs were removed makes sense for curated repositories
        # In regular repositories, it may be confusing (e.g., if PDFs are renamed)
        # In these cases, we may simply print a warning instead of modifying/removing records?
        if self.review_manager.settings.is_curated_masterdata_repo():
            self.__remove_records_if_pdf_no_longer_exists(
                search_operation=search_operation
            )

        pdfs_dir_feed = connector_utils.GeneralOriginFeed(
            source_operation=search_operation,
            source=self.search_source,
            feed_file=self.search_source.filename,
            update_only=False,
            key="file",
        )
        records = search_operation.review_manager.dataset.load_records_dict()
        grobid_service = search_operation.review_manager.get_grobid_service()
        grobid_service.start()

        pdfs_to_index = [
            x.relative_to(search_operation.review_manager.path)
            for x in self.pdfs_path.glob("**/*.pdf")
        ]

        # TODO : add parameter to switch the following on/off:
        # note: for curations, we want all pdfs indexed/merged separately,
        # in other projects, it is generally sufficient if the pdf is linked
        linked_pdf_paths = [Path(r["file"]) for r in records.values() if "file" in r]

        if search_operation.review_manager.force_mode:  # i.e., reindex all
            search_operation.review_manager.logger.info("Reindex all")

        batch_size = 20
        pdf_batches = [
            pdfs_to_index[i * batch_size : (i + 1) * batch_size]
            for i in range((len(pdfs_to_index) + batch_size - 1) // batch_size)
        ]
        nr_added, nr_changed = 0, 0
        for pdf_batch in pdf_batches:

            for record in pdfs_dir_feed.feed_records.values():
                record = self.__add_md_string(record_dict=record)

            for pdf_path in pdf_batch:

                if self.__is_broken_filepath(pdf_path=pdf_path):
                    continue

                if search_operation.review_manager.force_mode:
                    # i.e., reindex all
                    pass
                else:
                    if pdf_path in linked_pdf_paths:
                        # Otherwise: skip linked PDFs
                        continue

                    if pdf_path in [
                        Path(r["file"])
                        for r in pdfs_dir_feed.feed_records.values()
                        if "file" in r
                    ]:
                        continue

                new_record = self.__index_pdf(
                    search_operation=search_operation, pdf_path=pdf_path
                )

                new_record = self.__add_md_string(record_dict=new_record)

                # Note: identical md_string as a heuristic for duplicates
                potential_duplicates = [
                    r
                    for r in pdfs_dir_feed.feed_records.values()
                    if r["md_string"] == new_record["md_string"]
                    and not r["file"] == new_record["file"]
                ]
                if potential_duplicates:
                    search_operation.review_manager.logger.warning(
                        f" {colors.RED}skip record (PDF potential duplicate): "
                        f"{new_record['file']} {colors.END} "
                        f"({','.join([r['file'] for r in potential_duplicates])})"
                    )
                    continue

                pdfs_dir_feed.set_id(record_dict=new_record)

                prev_record_dict_version = {}
                if new_record["ID"] in pdfs_dir_feed.feed_records:
                    prev_record_dict_version = pdfs_dir_feed.feed_records[
                        new_record["ID"]
                    ]

                added = pdfs_dir_feed.add_record(
                    record=colrev.record.Record(data=new_record),
                )
                if added:
                    nr_added += 1

                elif self.review_manager.force_mode:
                    # Note : only re-index/update
                    changed = search_operation.update_existing_record(
                        records=records,
                        record_dict=new_record,
                        prev_record_dict_version=prev_record_dict_version,
                        source=self.search_source,
                    )
                    if changed:
                        nr_changed += 1

            for record in pdfs_dir_feed.feed_records.values():
                record.pop("md_string")

            pdfs_dir_feed.save_feed_file()

        if nr_added > 0:
            search_operation.review_manager.logger.info(
                f"{colors.GREEN}Retrieved {nr_added} records{colors.END}"
            )
        else:
            search_operation.review_manager.logger.info(
                f"{colors.GREEN}No additional records retrieved{colors.END}"
            )

        if self.review_manager.force_mode:
            if nr_changed > 0:
                self.review_manager.logger.info(
                    f"{colors.GREEN}Updated {nr_changed} records{colors.END}"
                )
            else:
                self.review_manager.logger.info(
                    f"{colors.GREEN}Records up-to-date{colors.END}"
                )

    @classmethod
    def heuristic(cls, filename: Path, data: str) -> dict:
        """Source heuristic for PDF directories (GROBID)"""

        result = {"confidence": 0.0}

        if filename.suffix == ".pdf" and not bws.BackwardSearchSource.heuristic(
            filename=filename, data=data
        ):
            result["confidence"] = 1.0
            return result

        return result

    def load_fixes(
        self,
        load_operation: colrev.ops.load.Load,
        source: colrev.settings.SearchSource,
        records: typing.Dict,
    ) -> dict:
        """Load fixes for PDF directories (GROBID)"""

        for record in records.values():
            if "grobid-version" in record:
                del record["grobid-version"]

        return records

    def prepare(
        self, record: colrev.record.Record, source: colrev.settings.SearchSource
    ) -> colrev.record.Record:
        """Source-specific preparation for PDF directories (GROBID)"""

        # TODO : if curated_repo, load journal/booktitle
        # from data package (in init() and compare in the following)

        # Typical error in old papers: title fields are equal to journal/booktitle fields
        if record.data.get("title", "no_title").lower() == record.data.get(
            "journal", "no_journal"
        ):
            record.remove_field(key="title", source="pdfs_dir_prepare")
            record.set_status(
                target_state=colrev.record.RecordState.md_needs_manual_preparation
            )
        if record.data.get("title", "no_title").lower() == record.data.get(
            "booktitle", "no_booktitle"
        ):
            record.remove_field(key="title", source="pdfs_dir_prepare")
            record.set_status(
                target_state=colrev.record.RecordState.md_needs_manual_preparation
            )

        return record


if __name__ == "__main__":
    pass
