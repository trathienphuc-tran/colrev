#!/usr/bin/env python3
import errno
import itertools
import json
import logging
import os
import re
import string
import typing
from pathlib import Path

import bibtexparser
import git
import pandas as pd
import yaml
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.customization import convert_to_unicode
from yaml import safe_load

from colrev_core import utils
from colrev_core.local_index import LocalIndex
from colrev_core.process import RecordState


class ReviewDataset:
    def __init__(self, REVIEW_MANAGER) -> None:
        self.REVIEW_MANAGER = REVIEW_MANAGER
        self.MAIN_REFERENCES_FILE = REVIEW_MANAGER.paths["MAIN_REFERENCES"]
        self.__git_repo = git.Repo(self.REVIEW_MANAGER.path)

    def load_sources(self) -> list:
        """Load the source details"""

        if self.REVIEW_MANAGER.paths["SOURCES"].is_file():
            with open(self.REVIEW_MANAGER.paths["SOURCES"]) as f:
                sources_df = pd.json_normalize(safe_load(f))
                sources = sources_df.to_dict("records")
        else:
            self.REVIEW_MANAGER.logger.debug(
                "Sources file does not exist "
                f'{self.REVIEW_MANAGER.paths["SOURCES"].name}'
            )
            sources = []
        return sources

    def save_sources(self, sources: list) -> None:
        """Save the source details"""

        sources_df = pd.DataFrame(sources)
        orderedCols = [
            "filename",
            "search_type",
            "source_name",
            "source_url",
            "search_parameters",
            "comment",
        ]
        for x in [x for x in sources_df.columns if x not in orderedCols]:
            orderedCols.append(x)
        sources_df = sources_df.reindex(columns=orderedCols)

        with open(self.REVIEW_MANAGER.paths["SOURCES"], "w") as f:
            yaml.dump(
                json.loads(sources_df.to_json(orient="records")),
                f,
                default_flow_style=False,
                sort_keys=False,
            )
        self.__git_repo.index.add([str(self.REVIEW_MANAGER.paths["SOURCES_RELATIVE"])])
        return

    def get_record_state_list_from_file_obj(self, file_object) -> list:
        return [
            self.__get_record_status_item(record_header_str)
            for record_header_str in self.__read_next_record_header_str(file_object)
        ]

    def get_record_state_list(self) -> list:
        """Get the record_state_list"""

        if not self.MAIN_REFERENCES_FILE.is_file():
            return []
        return [
            self.__get_record_status_item(record_header_str)
            for record_header_str in self.__read_next_record_header_str()
        ]

    def get_record_header_list(self) -> list:
        """Get the record_header_list"""

        if not self.MAIN_REFERENCES_FILE.is_file():
            return []
        return [
            self.__get_record_header_item(record_header_str)
            for record_header_str in self.__read_next_record_header_str()
        ]

    def get_states_set(self, record_state_list: list = None) -> set:
        """Get the record_states_set"""

        if not self.MAIN_REFERENCES_FILE.is_file():
            return set()
        if record_state_list is None:
            record_state_list = self.get_record_state_list()
        return {el[1] for el in record_state_list}

    def __get_record_status_item(self, r_header: str) -> list:
        rhlines = r_header.split("\n")
        rhl0, rhl1, rhl2 = (
            line[line.find("{") + 1 : line.rfind(",")] for line in rhlines[0:3]
        )
        ID = rhl0
        if "status" not in rhlines[2]:
            raise StatusFieldValueError(ID, "status", "NA")
        status = rhl2[:-1]  # to replace the trailing }
        return [ID, status]

    def __get_record_header_item(self, r_header: str) -> list:
        items = r_header.split("\n")[0:8]

        ID = items.pop(0)

        origin = items.pop(0)
        if "origin" not in origin:
            raise RecordFormatError(f"{ID} has status=NA")
        origin = origin[origin.find("{") + 1 : origin.rfind("}")]

        status = items.pop(0)
        if "status" not in status:
            raise StatusFieldValueError(ID, "status", "NA")
        status = status[status.find("{") + 1 : status.rfind("}")]

        excl_criteria, file = "", ""
        while items:
            item = items.pop(0)

            # excl_criteria can only be in line 4 (but it is optional)
            if "excl_criteria" in item:
                excl_criteria = item[item.find("{") + 1 : item.rfind("}")]
                continue

            # file is optional and could be in lines 4-7
            if "file" in item:
                file = item[item.find("{") + 1 : item.rfind("}")]

        return [ID, origin, status, excl_criteria, file]

    def load_records(self, init: bool = False) -> typing.List[dict]:
        """Get the records (requires REVIEW_MANAGER.notify(...))"""

        if self.REVIEW_MANAGER.notified_next_process is None:
            raise ReviewManagerNotNofiedError()

        from bibtexparser.bparser import BibTexParser
        from bibtexparser.customization import convert_to_unicode

        if self.MAIN_REFERENCES_FILE.is_file():
            with open(self.MAIN_REFERENCES_FILE) as target_db:
                bib_db = BibTexParser(
                    customization=convert_to_unicode,
                    ignore_nonstandard_types=False,
                    common_strings=True,
                ).parse_file(target_db, partial=True)

                records = bib_db.entries

                # Cast status to Enum
                records = [
                    {k: RecordState[v] if ("status" == k) else v for k, v in r.items()}
                    for r in records
                ]

                # DOIs are case sensitive -> use upper case.
                records = [
                    {k: v.upper() if ("doi" == k) else v for k, v in r.items()}
                    for r in records
                ]

        else:
            if init:
                records = []
            else:
                raise FileNotFoundError(
                    errno.ENOENT, os.strerror(errno.ENOENT), self.MAIN_REFERENCES_FILE
                )

        return records

    def save_records(self, records: typing.List[dict]) -> None:
        """Save the records"""

        # Casting to string (in particular the RecordState Enum)
        records = [{k: str(v) for k, v in r.items()} for r in records]

        records.sort(key=lambda x: x["ID"])

        bib_db = BibDatabase()
        bib_db.entries = records

        bibtex_str = bibtexparser.dumps(bib_db, self.get_bibtex_writer())

        with open(self.MAIN_REFERENCES_FILE, "w") as out:
            out.write(bibtex_str)

        # Casting to RecordState (in case the records are used afterwards)
        records = [
            {k: RecordState[v] if ("status" == k) else v for k, v in r.items()}
            for r in records
        ]

        # DOIs are case sensitive -> use upper case.
        records = [
            {k: v.upper() if ("doi" == k) else v for k, v in r.items()} for r in records
        ]

        return

    def reprocess_id(self, id: str) -> None:
        """Remove an ID (set of IDs) from the bib_db (for reprocessing)"""

        saved_args = locals()

        if "all" == id:
            # logging.info("Removing/reprocessing all records")
            os.remove(self.MAIN_REFERENCES_FILE)
            self.__git_repo.index.remove(
                [str(self.REVIEW_MANAGER.paths["MAIN_REFERENCES_RELATIVE"])],
                working_tree=True,
            )
        else:
            records = self.load_records()
            records = [x for x in records if id != x["ID"]]
            self.save_records(records)
            self.add_record_changes()

        self.REVIEW_MANAGER.create_commit("Reprocess", saved_args=saved_args)

        return

    def get_bibtex_writer(self) -> BibTexWriter:

        writer = BibTexWriter()

        writer.contents = ["entries"]
        # Note: IDs should be at the beginning to facilitate git versioning
        # order: hard-coded in get_record_status_item()
        writer.display_order = [
            "origin",  # must be in second line
            "status",  # must be in third line
            "metadata_source",
            "excl_criteria",
            "man_prep_hints",
            "pdf_processed",
            "file",  # Note : do not change this order (parsers rely on it)
            "pdf_hash",
            "potential_dupes",
            "doi",
            "grobid-version",
            "dblp_key",
            "wos_accession_number",
            "source_url",
            "author",
            "booktitle",
            "journal",
            "title",
            "year",
            "editor",
            "number",
            "pages",
            "series",
            "volume",
            "abstract",
            "book-author",
            "book-group-author",
        ]

        writer.order_entries_by = "ID"
        writer.add_trailing_comma = True
        writer.align_values = True
        writer.indent = "  "
        return writer

    def set_IDs(
        self, records: typing.List[dict] = [], selected_IDs: list = None
    ) -> typing.List[dict]:
        """Set the IDs of records according to predefined formats or
        according to the LocalIndex"""

        if len(records) == 0:
            records = self.load_records()

        ID_list = [record["ID"] for record in records]

        for record in records:
            if selected_IDs is not None:
                if record["ID"] not in selected_IDs:
                    continue
                if "LOCAL_INDEX" == record.get("metadata_source", ""):
                    continue
            elif str(record["status"]) not in [
                str(RecordState.md_imported),
                str(RecordState.md_prepared),
            ]:
                continue

            old_id = record["ID"]
            new_id = self.__generate_ID_blacklist(
                record, ID_list, record_in_bib_db=True, raise_error=False
            )
            record.update(ID=new_id)
            ID_list.append(new_id)
            if old_id != new_id:
                self.REVIEW_MANAGER.report_logger.info(f"set_ID({old_id}) to {new_id}")
                if old_id in ID_list:
                    ID_list.remove(old_id)

        records = sorted(records, key=lambda d: d["ID"])

        self.save_records(records)

        # Note : temporary fix
        # (to prevent failing format checks caused by special characters)
        records = self.load_records()
        self.save_records(records)
        self.add_record_changes()

        return records

    def propagated_ID(self, ID: str) -> bool:
        """Check whether an ID has been propagated"""

        propagated = False

        if self.REVIEW_MANAGER.paths["DATA"].is_file():
            # Note: this may be redundant, but just to be sure:
            data = pd.read_csv(self.REVIEW_MANAGER.paths["DATA"], dtype=str)
            if ID in data["ID"].tolist():
                propagated = True

        # TODO: also check data_pages?

        return propagated

    def __generate_ID(
        self,
        record: dict,
        records: typing.List[dict] = [],
        record_in_bib_db: bool = False,
        raise_error: bool = True,
    ) -> str:
        """Generate a record ID according to the predefined format"""

        if len(records) == 0:
            ID_blacklist = [record["ID"] for record in records]
        else:
            ID_blacklist = []
        ID = self.__generate_ID_blacklist(
            record, ID_blacklist, record_in_bib_db, raise_error
        )
        return ID

    def __generate_ID_blacklist(
        self,
        record: dict,
        ID_blacklist: list = None,
        record_in_bib_db: bool = False,
        raise_error: bool = True,
    ) -> str:
        """Generate a blacklist to avoid setting duplicate IDs"""

        from colrev_core.prep import Preparation
        from colrev_core.local_index import LocalIndex

        # Make sure that IDs that have been propagated to the
        # screen or data will not be replaced
        # (this would break the chain of evidence)
        if raise_error:
            if self.propagated_ID(record["ID"]):
                raise CitationKeyPropagationError(
                    "WARNING: do not change IDs that have been "
                    + f'propagated to {self.REVIEW_MANAGER.paths["DATA"]} '
                    + f'({record["ID"]})'
                )

        LOCAL_INDEX = LocalIndex()
        PREPARATION = Preparation(notify=False)
        try:
            retrieved_record = LOCAL_INDEX.retrieve_record_from_index(record)
            temp_ID = retrieved_record["ID"]
        except LocalIndex.RecordNotInIndexException:
            pass

            if "" != record.get("author", record.get("editor", "")):
                authors = PREPARATION.format_author_field(
                    record.get("author", record.get("editor", "Anonymous"))
                ).split(" and ")
            else:
                authors = ["Anonymous"]

            # Use family names
            for author in authors:
                if "," in author:
                    author = author.split(",")[0]
                else:
                    author = author.split(" ")[0]

            ID_PATTERN = self.REVIEW_MANAGER.config["ID_PATTERN"]

            assert ID_PATTERN in ["FIRST_AUTHOR_YEAR", "THREE_AUTHORS_YEAR"]
            if "FIRST_AUTHOR_YEAR" == ID_PATTERN:
                temp_ID = (
                    f'{author.replace(" ", "")}{str(record.get("year", "NoYear"))}'
                )

            if "THREE_AUTHORS_YEAR" == ID_PATTERN:
                temp_ID = ""
                indices = len(authors)
                if len(authors) > 3:
                    indices = 3
                for ind in range(0, indices):
                    temp_ID = temp_ID + f'{authors[ind].split(",")[0].replace(" ", "")}'
                if len(authors) > 3:
                    temp_ID = temp_ID + "EtAl"
                temp_ID = temp_ID + str(record.get("year", "NoYear"))

            if temp_ID.isupper():
                temp_ID = temp_ID.capitalize()
            # Replace special characters
            # (because IDs may be used as file names)
            temp_ID = utils.remove_accents(temp_ID)
            temp_ID = re.sub(r"\(.*\)", "", temp_ID)
            temp_ID = re.sub("[^0-9a-zA-Z]+", "", temp_ID)

        if ID_blacklist is not None:
            if record_in_bib_db:
                # allow IDs to remain the same.
                other_ids = ID_blacklist
                # Note: only remove it once. It needs to change when there are
                # other records with the same ID
                if record["ID"] in other_ids:
                    other_ids.remove(record["ID"])
            else:
                # ID can remain the same, but it has to change
                # if it is already in bib_db
                other_ids = ID_blacklist

            order = 0
            letters = list(string.ascii_lowercase)
            next_unique_ID = temp_ID
            appends: list = []
            while next_unique_ID in other_ids:
                if len(appends) == 0:
                    order += 1
                    appends = [p for p in itertools.product(letters, repeat=order)]
                next_unique_ID = temp_ID + "".join(list(appends.pop(0)))
            temp_ID = next_unique_ID

        return temp_ID

    def __read_next_record_header_str(
        self, file_object=None, HEADER_LENGTH: int = 9
    ) -> typing.Iterator[str]:
        if file_object is None:
            file_object = open(self.MAIN_REFERENCES_FILE)
        data = ""
        first_entry_processed = False
        header_line_count = 0
        while True:
            line = file_object.readline()
            if not line:
                break
            if line[:1] == "%" or line == "\n":
                continue
            if line[:1] != "@":
                if header_line_count < HEADER_LENGTH:
                    header_line_count = header_line_count + 1
                    data += line
            else:
                if "@comment" not in line:
                    if first_entry_processed:
                        yield data
                        header_line_count = 0
                    else:
                        first_entry_processed = True
                data = line
        if "@comment" not in data:
            yield data

    def __read_next_record_str(self, file_object=None) -> typing.Iterator[str]:
        if file_object is None:
            file_object = open(self.MAIN_REFERENCES_FILE)
        data = ""
        first_entry_processed = False
        while True:
            line = file_object.readline()
            if not line:
                break
            if line[:1] == "%" or line == "\n":
                continue
            if line[:1] != "@":
                data += line
            else:
                if first_entry_processed:
                    yield data
                else:
                    first_entry_processed = True
                data = line
        yield data

    def read_next_record(self, conditions: list = None) -> typing.Iterator[dict]:
        records = []
        with open(self.MAIN_REFERENCES_FILE) as f:
            for record_string in self.__read_next_record_str(f):
                parser = BibTexParser(customization=convert_to_unicode)
                db = bibtexparser.loads(record_string, parser=parser)
                record = db.entries[0]
                record["status"] = RecordState[record["status"]]
                if conditions is not None:
                    for condition in conditions:
                        for key, value in condition.items():
                            if str(value) == str(record[key]):
                                records.append(record)
                else:
                    records.append(record)
        yield from records

    def replace_field(self, IDs: list, key: str, val_str: str) -> None:

        val = val_str.encode("utf-8")
        current_ID_str = "NA"
        with open(self.MAIN_REFERENCES_FILE, "r+b") as fd:
            seekpos = fd.tell()
            line = fd.readline()
            while line:
                if b"@" in line[:3]:
                    current_ID = line[line.find(b"{") + 1 : line.rfind(b",")]
                    current_ID_str = current_ID.decode("utf-8")

                replacement = None
                if current_ID_str in IDs:
                    if line.lstrip()[: len(key)].decode("utf-8") == key:
                        replacement = line[: line.find(b"{") + 1] + val + b"},\n"

                if replacement:
                    if len(replacement) == len(line):
                        fd.seek(seekpos)
                        fd.write(replacement)
                        fd.flush()
                        os.fsync(fd)
                    else:
                        remaining = fd.read()
                        fd.seek(seekpos)
                        fd.write(replacement)
                        seekpos = fd.tell()
                        fd.flush()
                        os.fsync(fd)
                        fd.write(remaining)
                        fd.truncate()  # if the replacement is shorter...
                        fd.seek(seekpos)
                        line = fd.readline()
                    IDs.remove(current_ID_str)
                    if 0 == len(IDs):
                        return
                seekpos = fd.tell()
                line = fd.readline()
        return

    def update_record_by_ID(self, new_record: dict, delete: bool = False) -> None:

        ID = new_record["ID"]
        new_record["status"] = str(new_record["status"])
        bib_db = BibDatabase()
        bib_db.entries = [new_record]
        replacement = bibtexparser.dumps(bib_db, self.get_bibtex_writer())

        current_ID_str = "NA"
        with open(self.MAIN_REFERENCES_FILE, "r+b") as fd:
            seekpos = fd.tell()
            line = fd.readline()
            while line:
                if b"@" in line[:3]:
                    current_ID = line[line.find(b"{") + 1 : line.rfind(b",")]
                    current_ID_str = current_ID.decode("utf-8")

                if current_ID_str == ID:
                    line = fd.readline()
                    while (
                        b"@" not in line[:3] and line
                    ):  # replace: drop the current record
                        line = fd.readline()
                    remaining = line + fd.read()
                    fd.seek(seekpos)
                    if not delete:
                        fd.write(replacement.encode("utf-8"))
                    seekpos = fd.tell()
                    fd.flush()
                    os.fsync(fd)
                    fd.write(remaining)
                    fd.truncate()  # if the replacement is shorter...
                    fd.seek(seekpos)
                    line = fd.readline()
                    return

                seekpos = fd.tell()
                line = fd.readline()
        return

    def save_record_list_by_ID(
        self, record_list: list, append_new: bool = False
    ) -> None:

        if record_list == []:
            return

        # Casting to string (in particular the RecordState Enum)
        record_list = [{k: str(v) for k, v in r.items()} for r in record_list]

        bib_db = BibDatabase()
        bib_db.entries = record_list
        parsed = bibtexparser.dumps(bib_db, self.get_bibtex_writer())

        record_list = [
            {
                "ID": item[item.find("{") + 1 : item.find(",")],
                "record": "@" + item + "\n",
            }
            for item in parsed.split("\n@")
        ]
        # Correct the first and last items
        record_list[0]["record"] = "@" + record_list[0]["record"][2:]
        record_list[-1]["record"] = record_list[-1]["record"][:-1]

        current_ID_str = "NOTSET"
        if self.MAIN_REFERENCES_FILE.is_file():
            with open(self.MAIN_REFERENCES_FILE, "r+b") as fd:
                seekpos = fd.tell()
                line = fd.readline()
                while line:
                    if b"@" in line[:3]:
                        current_ID = line[line.find(b"{") + 1 : line.rfind(b",")]
                        current_ID_str = current_ID.decode("utf-8")
                    if current_ID_str in [x["ID"] for x in record_list]:
                        replacement = [x["record"] for x in record_list][0]
                        record_list = [
                            x for x in record_list if x["ID"] != current_ID_str
                        ]
                        line = fd.readline()
                        while (
                            b"@" not in line[:3] and line
                        ):  # replace: drop the current record
                            line = fd.readline()
                        remaining = line + fd.read()
                        fd.seek(seekpos)
                        fd.write(replacement.encode("utf-8"))
                        seekpos = fd.tell()
                        fd.flush()
                        os.fsync(fd)
                        fd.write(remaining)
                        fd.truncate()  # if the replacement is shorter...
                        fd.seek(seekpos)

                    seekpos = fd.tell()
                    line = fd.readline()

        if len(record_list) > 0:
            if append_new:
                with open(self.MAIN_REFERENCES_FILE, "a") as m_refs:
                    for replacement in record_list:
                        m_refs.write(replacement["record"])

            else:
                self.REVIEW_MANAGER.report_logger.error(
                    "records not written to file: " f'{[x["ID"] for x in record_list]}'
                )

        self.add_record_changes()

        return

    def format_main_references(self) -> bool:
        from colrev_core.prep import Preparation
        from colrev_core.process import FormatProcess

        PREPARATION = Preparation(notify=False)

        FormatProcess()  # to notify

        records = self.load_records()
        for record in records:
            if "status" not in record:
                print(f'Error: no status field in record ({record["ID"]})')
                continue
            if record["status"] == RecordState.md_needs_manual_preparation:
                prior = record.get("man_prep_hints", "")
                if "man_prep_hints" in record:
                    del record["man_prep_hints"]
                record = PREPARATION.log_notifications(record, record.copy())
                record = PREPARATION.update_metadata_status(record)
                if record["status"] == RecordState.md_prepared:
                    record["metadata_source"] = "MANUAL"
                if RecordState.md_needs_manual_preparation == record["status"]:
                    if "change-score" in prior:
                        record["man_prep_hints"] += (
                            "; " + prior[prior.find("change-score") :]
                        )
                else:
                    if record.get("man_prep_hints", "NA") == "":
                        del record["man_prep_hints"]

            if record["status"] == RecordState.pdf_prepared:
                if "pdf_prep_hints" in record:
                    del record["pdf_prep_hints"]

        records = sorted(records, key=lambda d: d["ID"])
        self.save_records(records)
        CHANGED = self.REVIEW_MANAGER.paths["MAIN_REFERENCES_RELATIVE"] in [
            r.a_path for r in self.__git_repo.index.diff(None)
        ]
        return CHANGED

    def retrieve_data(self, prior: dict) -> dict:
        from colrev_core.process import ProcessModel

        data: dict = {
            "missing_file": [],
            "pdf_not_exists": [],
            "status_fields": [],
            "status_transitions": [],
            "start_states": [],
            "exclusion_criteria_list": [],
            "IDs": [],
            "entries_without_origin": [],
            "record_links_in_bib": [],
            "persisted_IDs": [],
            "origin_list": [],
            "curated_records": [],
        }

        with open(self.MAIN_REFERENCES_FILE) as f:
            for record_string in self.__read_next_record_str(f):
                ID, file, status, excl_crit, origin = (
                    "NA",
                    "NA",
                    "NA",
                    "not_set",
                    "NA",
                )

                # TODO: this can be done more efficiently
                # because we fixed the order of the first rows.
                for line in record_string.split("\n"):
                    if "@Comment" in line:
                        ID = "Comment"
                        break
                    if "@" in line[:3]:
                        ID = line[line.find("{") + 1 : line.rfind(",")]
                    if "file" == line.lstrip()[:4]:
                        file = line[line.find("{") + 1 : line.rfind("}")]
                    if "status" == line.lstrip()[:6]:
                        status = line[line.find("{") + 1 : line.rfind("}")]
                    if "excl_criteria" == line.lstrip()[:13]:
                        excl_crit = line[line.find("{") + 1 : line.rfind("}")]
                    if "origin" == line.strip()[:6]:
                        origin = line[line.find("{") + 1 : line.rfind("}")]
                if "Comment" == ID:
                    continue
                if "NA" == ID:
                    logging.error(f"Skipping record without ID: {record_string}")
                    continue

                data["IDs"].append(ID)

                for org in origin.split(";"):
                    data["origin_list"].append([ID, org])

                # TODO: determine succeeding states from state machine
                if status in [
                    str(RecordState.md_processed),
                    str(RecordState.rev_prescreen_excluded),
                    str(RecordState.rev_prescreen_included),
                    str(RecordState.pdf_needs_manual_retrieval),
                    str(RecordState.pdf_imported),
                    str(RecordState.pdf_not_available),
                    str(RecordState.pdf_needs_manual_preparation),
                    str(RecordState.pdf_prepared),
                    str(RecordState.rev_excluded),
                    str(RecordState.rev_included),
                    str(RecordState.rev_synthesized),
                ]:
                    for origin_part in origin.split(";"):
                        data["persisted_IDs"].append([origin_part, ID])

                if file != "NA":
                    if not all(Path(f).is_file() for f in file.split(";")):
                        data["pdf_not_exists"].append(ID)

                if origin != "NA":
                    for org in origin.split(";"):
                        data["record_links_in_bib"].append(org)
                else:
                    data["entries_without_origin"].append(ID)

                data["status_fields"].append(status)

                # TODO: determine succeeding states from state machine
                # excluding pdf_not_available
                file_required_status = [
                    str(RecordState.pdf_imported),
                    str(RecordState.pdf_needs_manual_preparation),
                    str(RecordState.pdf_prepared),
                    str(RecordState.rev_excluded),
                    str(RecordState.rev_included),
                    str(RecordState.rev_synthesized),
                ]

                if (" file  " not in record_string) and (
                    status in file_required_status
                ):
                    data["missing_file"].append(ID)

                if "not_set" != excl_crit:
                    ec_case = [ID, status, excl_crit]
                    data["exclusion_criteria_list"].append(ec_case)

                # TODO: the origins of an record could be in multiple status
                if "status" in prior:
                    prior_status = [
                        stat
                        for (org, stat) in prior["status"]
                        if org in origin.split(";")
                    ]
                else:
                    prior_status = []

                if "LOCAL_INDEX" in record_string:
                    parser = BibTexParser(customization=convert_to_unicode)
                    db = bibtexparser.loads(record_string, parser=parser)
                    r = db.entries[0]
                    if r["ID"] == ID:
                        data["curated_records"].append(r)

                status_transition = {}
                if len(prior_status) == 0:
                    status_transition[ID] = "load"
                else:
                    proc_transition_list: list = [
                        x["trigger"]
                        for x in ProcessModel.transitions
                        if str(x["source"]) == prior_status[0]
                        and str(x["dest"]) == status
                    ]
                    if len(proc_transition_list) == 0 and prior_status[0] != status:
                        data["start_states"].append(prior_status[0])
                        if prior_status[0] not in [str(x) for x in RecordState]:
                            raise StatusFieldValueError(ID, "status", prior_status[0])
                        if status not in [str(x) for x in RecordState]:
                            raise StatusFieldValueError(ID, "status", status)

                        raise StatusTransitionError(
                            f"invalid state transition ({ID}):"
                            + f" {prior_status[0]} to {status}"
                        )
                    if 0 == len(proc_transition_list):
                        status_transition[ID] = "load"
                    else:
                        proc_transition = proc_transition_list.pop()
                        status_transition[ID] = proc_transition

                data["status_transitions"].append(status_transition)

        return data

    def retrieve_prior(self) -> dict:
        import io

        MAIN_REFERENCES_RELATIVE = self.REVIEW_MANAGER.paths["MAIN_REFERENCES_RELATIVE"]
        revlist = (
            (
                commit.hexsha,
                (commit.tree / str(MAIN_REFERENCES_RELATIVE)).data_stream.read(),
            )
            for commit in self.__git_repo.iter_commits(
                paths=str(MAIN_REFERENCES_RELATIVE)
            )
        )
        prior: dict = {"status": [], "persisted_IDs": [], "curated_records": []}
        filecontents = list(revlist)[0][1]
        prior_db_str = io.StringIO(filecontents.decode("utf-8"))
        for record_string in self.__read_next_record_str(prior_db_str):

            ID, status, origin = "NA", "NA", "NA"
            for line in record_string.split("\n"):
                if "@" in line[:3]:
                    ID = line[line.find("{") + 1 : line.rfind(",")]
                if "status" == line.lstrip()[:6]:
                    status = line[line.find("{") + 1 : line.rfind("}")]
                if "origin" == line.strip()[:6]:
                    origin = line[line.find("{") + 1 : line.rfind("}")]
            if "NA" != ID:
                for orig in origin.split(";"):
                    prior["status"].append([orig, status])
                    if str(RecordState.md_processed) == status:
                        prior["persisted_IDs"].append([orig, ID])

            else:
                logging.error(f"record without ID: {record_string}")
            if "LOCAL_INDEX" in record_string:
                parser = BibTexParser(customization=convert_to_unicode)
                db = bibtexparser.loads(record_string, parser=parser)
                r = db.entries[0]
                if r["ID"] == ID:
                    prior["curated_records"].append(r)

        return prior

    # def read_next_record(file_object) -> typing.Iterator[str]:
    #     data = ""
    #     first_record_processed = False
    #     while True:
    #         line = file_object.readline()
    #         if not line:
    #             break
    #         if line[:1] == "%" or line == "\n":
    #             continue
    #         if line[:1] != "@":
    #             data += line
    #         else:
    #             if first_record_processed:
    #                 yield data
    #             else:
    #                 first_record_processed = True
    #             data = line
    #     yield data

    def retrieve_IDs_from_bib(self, file_path: Path) -> list:
        assert file_path.suffix == ".bib"
        IDs = []
        with open(file_path) as f:
            line = f.readline()
            while line:
                if "@" in line[:5]:
                    ID = line[line.find("{") + 1 : line.rfind(",")]
                    IDs.append(ID.lstrip())
                line = f.readline()
        return IDs

    # CHECKS --------------------------------------------------------------

    def check_main_references_duplicates(self, data: dict) -> None:

        if not len(data["IDs"]) == len(set(data["IDs"])):
            duplicates = [ID for ID in data["IDs"] if data["IDs"].count(ID) > 1]
            if len(duplicates) > 20:
                raise DuplicatesError(
                    "Duplicates in MAIN_REFERENCES: "
                    f"({','.join(duplicates[0:20])}, ...)"
                )
            else:
                raise DuplicatesError(
                    f"Duplicates in MAIN_REFERENCES: {','.join(duplicates)}"
                )
        return

    def check_main_references_origin(self, prior: dict, data: dict) -> None:
        # Check whether each record has an origin
        if not len(data["entries_without_origin"]) == 0:
            raise OriginError(
                f"Entries without origin: {', '.join(data['entries_without_origin'])}"
            )

        # Check for broken origins
        search_dir = self.REVIEW_MANAGER.paths["SEARCHDIR"]
        all_record_links = []
        for bib_file in search_dir.glob("*.bib"):
            search_IDs = self.retrieve_IDs_from_bib(bib_file)
            for x in search_IDs:
                all_record_links.append(bib_file.name + "/" + x)
        delta = set(data["record_links_in_bib"]) - set(all_record_links)
        if len(delta) > 0:
            raise OriginError(f"broken origins: {delta}")

        # Check for non-unique origins
        origins = [x[1] for x in data["origin_list"]]
        non_unique_origins = []
        for org in origins:
            if origins.count(org) > 1:
                non_unique_origins.append(org)
        if non_unique_origins:
            for ID, org in data["origin_list"]:
                if org in non_unique_origins:
                    raise OriginError(f'Non-unique origin: origin="{org}"')

        # Check for removed origins
        # TODO !!!!
        # Raise an exception if origins were removed
        # prior_origins = [x[0] for x in prior['status']]
        # current_origins = [x[1] for x in data['origin_list']]
        # print(len(prior_origins))
        # print(len(current_origins))
        # print(set(prior_origins).difference(set(current_origins)))
        # print(set(current_origins).difference(set(prior_origins)))
        # print(pp.pformat(prior))
        # # print(pp.pformat(data))
        # input('stop')
        # for prior_origin, prior_id in prior["persisted_IDs"]:
        #     # TBD: notify if the origin no longer exists?
        #     for new_origin, new_id in data["persisted_IDs"]:
        #         if new_origin == prior_origin:
        #             if new_id != prior_id:
        #                 logging.error(
        #                     "ID of processed record changed from"
        #                     f" {prior_id} to {new_id}"
        #                 )
        #                 check_propagated_IDs(prior_id, new_id)
        #                 STATUS = FAIL
        return

    def check_main_references_status_fields(self, data: dict) -> None:
        # Check status fields
        status_schema = [str(x) for x in RecordState]
        stat_diff = set(data["status_fields"]).difference(status_schema)
        if stat_diff:
            raise FieldError(f"status field(s) {stat_diff} not in {status_schema}")
        return

    def check_status_transitions(self, data: dict) -> None:
        if len(set(data["start_states"])) > 1:
            raise StatusTransitionError(
                "multiple transitions from different "
                f'start states ({set(data["start_states"])})'
            )
        return

    def __get_excl_criteria(self, ec_string: str) -> list:
        return [ec.split("=")[0] for ec in ec_string.split(";") if ec != "NA"]

    def check_corrections_of_curated_records(self, prior: dict, data: dict) -> None:
        from colrev_core.review_manager import ReviewManager
        from dictdiffer import diff

        self.LOCAL_INDEX = LocalIndex()
        essential_md_keys = [
            "title",
            "author",
            "journal",
            "year",
            "booktitle",
            "number",
            "volume",
            "issue",
            "author",
            "doi",
        ]
        for curated_record in list(data["curated_records"]):
            # identify curated records for which essential metadata is changed
            prior_crl = [
                x for x in prior["curated_records"] if x["ID"] == curated_record["ID"]
            ]
            if len(prior_crl) != 1:
                continue
            prior_cr = prior_crl.pop()
            if not all(
                prior_cr.get(k, "NA") == curated_record.get(k, "NA")
                for k in essential_md_keys
            ):

                # retrieve record from index to identify origin repositories
                indexed_record = self.LOCAL_INDEX.retrieve_record_from_index(
                    curated_record
                )
                print(indexed_record["source_url"])
                CUR_REPO_MANAGER = ReviewManager(indexed_record["source_url"])
                changes = diff(indexed_record, curated_record)
                # push changes to the other repo (update the record in main references
                CUR_REPO_MANAGER.apply_corrections(indexed_record, changes)

        return

    def check_main_references_screen(self, data: dict) -> None:

        # Check screen
        # Note: consistency of inclusion_2=yes -> inclusion_1=yes
        # is implicitly ensured through status
        # (screen2-included/excluded implies prescreen included!)

        if data["exclusion_criteria_list"]:
            exclusion_criteria = data["exclusion_criteria_list"][0][2]
            if exclusion_criteria != "NA":
                criteria = self.__get_excl_criteria(exclusion_criteria)
                pattern = "=(yes|no);".join(criteria) + "=(yes|no)"
                pattern_inclusion = "=no;".join(criteria) + "=no"
            else:
                criteria = ["NA"]
                pattern = "^NA$"
                pattern_inclusion = "^NA$"
            for [ID, status, excl_crit] in data["exclusion_criteria_list"]:
                # print([ID, status, excl_crit])
                if not re.match(pattern, excl_crit):
                    # Note: this should also catch cases of missing
                    # exclusion criteria
                    raise FieldError(
                        "Exclusion criteria field not matching "
                        f"pattern: {excl_crit} ({ID}; criteria: {criteria})"
                    )

                elif str(RecordState.rev_excluded) == status:
                    if ["NA"] == criteria:
                        if "NA" == excl_crit:
                            continue
                        else:
                            raise FieldError(f"excl_crit field not NA: {excl_crit}")

                    if "=yes" not in excl_crit:
                        logging.error(f"criteria: {criteria}")
                        raise FieldError(
                            "Excluded record with no exclusion_criterion violated: "
                            f"{ID}, {status}, {excl_crit}"
                        )

                # Note: we don't have to consider the cases of
                # status=retrieved/prescreen_included/prescreen_excluded
                # because they would not have exclusion_criteria.
                else:
                    if not re.match(pattern_inclusion, excl_crit):
                        raise FieldError(
                            "Included record with exclusion_criterion satisfied: "
                            f"{ID}, {status}, {excl_crit}"
                        )
        return

    def check_main_references_files(self, data: dict) -> None:

        # Check pdf files
        if len(data["missing_file"]) > 0:
            raise FieldError(
                "record with status requiring a PDF file but missing "
                + f'the path (file = ...): {data["missing_file"]}'
            )

        if len(data["pdf_not_exists"]) > 0:
            raise FieldError(f'record with broken file link: {data["pdf_not_exists"]}')

        return

    # def check_screen_data(screen, data):
    #     # Check consistency: data -> inclusion_2
    #     data_IDs = data['ID'].tolist()
    #     screen_IDs = \
    #         screen['ID'][screen['inclusion_2'] == 'yes'].tolist()
    #     violations = [ID for ID in set(
    #         data_IDs) if ID not in set(screen_IDs)]
    #     if len(violations) != 0:
    #         raise some error ('IDs in DATA not coded as inclusion_2=yes: ' +
    #               f'{violations}')
    #     return

    # def check_duplicates_data(data):
    #     # Check whether there are duplicate IDs in data.csv
    #     if not data['ID'].is_unique:
    #         raise some error (data[data.duplicated(['ID'])].ID.tolist())
    #     return

    # def check_id_integrity_data(data, IDs):
    #     # Check consistency: all IDs in data.csv in references.bib
    #     missing_IDs = [ID for
    #                    ID in data['ID'].tolist()
    #                    if ID not in IDs]
    #     if not len(missing_IDs) == 0:
    #         raise some error ('IDs in data.csv not in MAIN_REFERENCES: ' +
    #               str(set(missing_IDs)))
    #     return

    def check_propagated_IDs(self, prior_id: str, new_id: str) -> list:

        ignore_patterns = [
            ".git",
            "config.ini",
            "report.log",
            ".pre-commit-config.yaml",
        ]

        text_formats = [".txt", ".csv", ".md", ".bib", ".yaml"]
        notifications = []
        for root, dirs, files in os.walk(os.getcwd(), topdown=False):
            for name in files:
                if any((x in name) or (x in root) for x in ignore_patterns):
                    continue
                if prior_id in name:
                    notifications.append(
                        f"Old ID ({prior_id}, changed to {new_id} in the "
                        f"MAIN_REFERENCES) found in filepath: {name}"
                    )

                if not any(name.endswith(x) for x in text_formats):
                    logging.debug(f"Skipping {name}")
                    continue
                logging.debug(f"Checking {name}")
                if name.endswith(".bib"):
                    retrieved_IDs = self.retrieve_IDs_from_bib(
                        Path(os.path.join(root, name))
                    )
                    if prior_id in retrieved_IDs:
                        notifications.append(
                            f"Old ID ({prior_id}, changed to {new_id} in "
                            f"the MAIN_REFERENCES) found in file: {name}"
                        )
                else:
                    with open(os.path.join(root, name)) as f:
                        line = f.readline()
                        while line:
                            if name.endswith(".bib") and "@" in line[:5]:
                                line = f.readline()
                            if prior_id in line:
                                notifications.append(
                                    f"Old ID ({prior_id}, to {new_id} in "
                                    f"the MAIN_REFERENCES) found in file: {name}"
                                )
                            line = f.readline()
            for name in dirs:
                if any((x in name) or (x in root) for x in ignore_patterns):
                    continue
                if prior_id in name:
                    notifications.append(
                        f"Old ID ({prior_id}, changed to {new_id} in the "
                        f"MAIN_REFERENCES) found in filepath: {name}"
                    )
        return notifications

    def check_persisted_ID_changes(self, prior: dict, data: dict) -> None:
        if "persisted_IDs" not in prior:
            return
        for prior_origin, prior_id in prior["persisted_IDs"]:
            if prior_origin not in [x[0] for x in data["persisted_IDs"]]:
                # Note: this does not catch origins removed before md_processed
                raise OriginError(f"origin removed: {prior_origin}")
            for new_origin, new_id in data["persisted_IDs"]:
                if new_origin == prior_origin:
                    if new_id != prior_id:
                        notifications = self.check_propagated_IDs(prior_id, new_id)
                        notifications.append(
                            "ID of processed record changed from "
                            f"{prior_id} to {new_id}"
                        )
                        raise PropagatedIDChange(notifications)
        return

    def check_sources(self) -> None:
        import errno

        SOURCES = self.REVIEW_MANAGER.paths["SOURCES"]
        SEARCHDIR = self.REVIEW_MANAGER.paths["SEARCHDIR"]
        search_type_opts = self.REVIEW_MANAGER.search_type_opts

        if not SOURCES.is_file():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), SOURCES)

        with open(SOURCES) as f:
            sources_df = pd.json_normalize(safe_load(f))
            sources = sources_df.to_dict("records")

        for search_file in SEARCHDIR.glob("*.bib"):
            if str(search_file.name) not in [x["filename"] for x in sources]:
                raise SearchDetailsError(
                    "Search file not in sources.yaml " f"({search_file})"
                )

        date_regex = r"^\d{4}-\d{2}-\d{2}$"
        for search_record in sources:
            missing_cols = [
                x
                for x in [
                    "filename",
                    "search_type",
                    "source_name",
                    "source_url",
                    "search_parameters",
                    "comment",
                ]
                if x not in search_record
            ]

            if any(missing_cols):
                raise SearchDetailsError(
                    f"Missing columns in {SOURCES}: {missing_cols}"
                )

            search_record_filename = SEARCHDIR / Path(search_record["filename"])
            if not search_record_filename.is_file():
                logging.warning(
                    f'Search details without file: {search_record["filename"]}'
                )
                # raise SearchDetailsError('File not found: "
                #                       f"{search_record["filename"]}')

            if search_record["search_type"] not in search_type_opts:
                raise SearchDetailsError(
                    f'{search_record["search_type"]} not in {search_type_opts}'
                )
            if "completion_date" in search_record:
                if not re.search(date_regex, search_record["completion_date"]):
                    raise SearchDetailsError(
                        "completion date not matching YYYY-MM-DD format: "
                        f'{search_record["completion_date"]}'
                    )
            if "start_date" in search_record:
                if not re.search(date_regex, search_record["start_date"]):
                    raise SearchDetailsError(
                        "start_date date not matchin YYYY-MM-DD format: "
                        f'{search_record["start_date"]}'
                    )

        return

    # GIT operations -----------------------------------------------

    def get_repo(self) -> git.Repo:
        """Get the git repository object (requires REVIEW_MANAGER.notify(...))"""

        if self.REVIEW_MANAGER.notified_next_process is None:
            raise ReviewManagerNotNofiedError()
        return self.__git_repo

    def has_changes(self) -> bool:
        # TODO : allow for optional path (check whether there are changes for that file)
        return self.__git_repo.is_dirty()

    def add_changes(self, path: str) -> None:
        self.__git_repo.index.add([str(path)])
        return

    def create_commit(
        self, msg: str, author: git.Actor, committer: git.Actor, hook_skipping: bool
    ) -> None:
        self.__git_repo.index.commit(
            msg,
            author=author,
            committer=committer,
            skip_hooks=hook_skipping,
        )
        return

    def file_in_history(self, filepath: Path) -> bool:
        return str(filepath) in [x.path for x in self.__git_repo.head.commit.tree]

    def get_commit_message(self, commit_nr: int) -> str:
        master = self.__git_repo.head.reference
        assert commit_nr == 0  # TODO : implement other cases
        if commit_nr == 0:
            cmsg = master.commit.message
        return cmsg

    def add_record_changes(self) -> None:
        self.__git_repo.index.add(
            [str(self.REVIEW_MANAGER.paths["MAIN_REFERENCES_RELATIVE"])]
        )
        return

    def reset_log_if_no_changes(self) -> None:
        if not self.__git_repo.is_dirty():
            self.REVIEW_MANAGER.reset_log()
        return

    def get_last_commit_sha(self) -> str:
        return str(self.__git_repo.head.commit.hexsha)

    def get_tree_hash(self) -> str:
        hash = self.__git_repo.git.execute(["git", "write-tree"])
        return str(hash)


class SearchDetailsError(Exception):
    def __init__(
        self,
        msg,
    ):
        self.message = f" {msg}"
        super().__init__(self.message)


class StatusTransitionError(Exception):
    def __init__(self, msg):
        self.message = f" {msg}"
        super().__init__(self.message)


class StatusFieldValueError(Exception):
    def __init__(self, record: str, status_type: str, status_value: str):
        self.message = f"{status_type} set to '{status_value}' in {record}."
        super().__init__(self.message)


class RecordFormatError(Exception):
    def __init__(self, msg):
        self.message = f" {msg}"
        super().__init__(self.message)


class CitationKeyPropagationError(Exception):
    pass


class DuplicatesError(Exception):
    def __init__(self, msg):
        self.message = f" {msg}"
        super().__init__(self.message)


class OriginError(Exception):
    def __init__(self, msg):
        self.message = f" {msg}"
        super().__init__(self.message)


class FieldError(Exception):
    def __init__(self, msg):
        self.message = f" {msg}"
        super().__init__(self.message)


class PropagatedIDChange(Exception):
    def __init__(self, notifications):
        self.message = "\n".join(notifications)
        super().__init__(self.message)


class ReviewManagerNotNofiedError(Exception):
    def __init__(self):
        self.message = (
            "inform the review manager about the next process in advance"
            + " to avoid conflicts (run review_manager.notify(processing_function))"
        )
        super().__init__(self.message)


if __name__ == "__main__":
    pass
