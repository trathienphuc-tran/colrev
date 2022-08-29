#! /usr/bin/env python
import pprint
import time

import dictdiffer

import colrev.process


class Trace(colrev.process.Process):
    def __init__(self, *, review_manager):

        super().__init__(
            review_manager=review_manager,
            process_type=colrev.process.ProcessType.check,
        )

    def __lpad_multiline(self, *, s: str, lpad: int) -> str:
        lines = s.splitlines()
        return "\n".join(["".join([" " * lpad]) + line for line in lines])

    def main(self, *, ID: str) -> None:

        self.review_manager.logger.info(f"Trace record by ID: {ID}")

        records_file_relative = self.review_manager.paths["RECORDS_FILE_RELATIVE"]
        data = self.review_manager.paths["DATA"]

        revlist = self.review_manager.dataset.get_repo().iter_commits()

        _pp = pprint.PrettyPrinter(indent=4)

        prev_record: dict = {}
        prev_data = ""
        for commit in reversed(list(revlist)):
            commit_message_first_line = str(commit.message).partition("\n")[0]
            print(
                "\n\n"
                + time.strftime(
                    "%Y-%m-%d %H:%M",
                    time.gmtime(commit.committed_date),
                )
                + f" {commit} ".ljust(40, " ")
                + f" {commit_message_first_line} (by {commit.author.name})"
            )

            if str(records_file_relative) in commit.tree:
                filecontents = (
                    commit.tree / str(records_file_relative)
                ).data_stream.read()

                records_dict = self.review_manager.dataset.load_records_dict(
                    load_str=filecontents.decode("utf-8")
                )

                if ID not in records_dict:
                    continue
                record = records_dict[ID]

                if len(record) == 0:
                    print(f"record {ID} not in commit.")
                else:
                    diffs = list(dictdiffer.diff(prev_record, record))
                    if len(diffs) > 0:
                        for diff in diffs:
                            print(self.__lpad_multiline(s=_pp.pformat(diff), lpad=5))
                    prev_record = record

            if data in commit.tree:
                filecontents = (commit.tree / data).data_stream.read()
                for line in str(filecontents).split("\\n"):
                    if ID in line:
                        if line != prev_data:
                            print(f"Data: {line}")
                            prev_data = line


if __name__ == "__main__":
    pass
