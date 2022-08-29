#! /usr/bin/env python
import pkgutil
import re
import typing
from pathlib import Path

import colrev.built_in.search as built_in_search
import colrev.dataset
import colrev.exceptions as colrev_exceptions
import colrev.process
import colrev.settings


class Search(colrev.process.Process):

    built_in_scripts: typing.Dict[str, typing.Dict[str, typing.Any]] = {
        "search_crossref": {
            "endpoint": built_in_search.CrossrefSearchEndpoint,
        },
        "search_dblp": {
            "endpoint": built_in_search.DBLPSearchEndpoint,
        },
        "backward_search": {
            "endpoint": built_in_search.BackwardSearchEndpoint,
        },
        "search_colrev_project": {
            "endpoint": built_in_search.ColrevProjectSearchEndpoint,
        },
        "search_local_index": {
            "endpoint": built_in_search.IndexSearchEndpoint,
        },
        "search_pdfs_dir": {
            "endpoint": built_in_search.PDFSearchEndpoint,
        },
    }

    def __init__(
        self,
        *,
        review_manager,
        notify_state_transition_process=True,
    ):

        super().__init__(
            review_manager=review_manager,
            process_type=colrev.process.ProcessType.search,
            notify_state_transition_process=notify_state_transition_process,
        )

        self.sources = review_manager.settings.sources

        AdapterManager = self.review_manager.get_environment_service(
            service_identifier="AdapterManager"
        )
        self.search_scripts: typing.Dict[str, typing.Any] = AdapterManager.load_scripts(
            PROCESS=self,
            scripts=[
                s.search_script for s in self.sources if "endpoint" in s.search_script
            ],
        )

    def save_feed_file(self, records: dict, feed_file: Path) -> None:

        feed_file.parents[0].mkdir(parents=True, exist_ok=True)
        records = {
            str(r["ID"]).replace(" ", ""): {
                k.lower()
                .replace(" ", "_")
                .replace("id", "ID")
                .replace("entrytype", "ENTRYTYPE"): v
                for k, v in r.items()
            }
            for r in records.values()
        }
        colrev.dataset.Dataset.save_records_dict_to_file(
            records=records, save_path=feed_file
        )

    def parse_sources(self, *, query: str) -> list:
        if "WHERE " in query:
            sources = query[query.find("FROM ") + 5 : query.find(" WHERE")].split(",")
        elif "SCOPE " in query:
            sources = query[query.find("FROM ") + 5 : query.find(" SCOPE")].split(",")
        elif "WITH " in query:
            sources = query[query.find("FROM ") + 5 : query.find(" WITH")].split(",")
        else:
            sources = query[query.find("FROM ") + 5 :].split(",")
        sources = [s.lstrip().rstrip() for s in sources]
        return sources

    def parse_parameters(self, *, search_params: str) -> dict:

        query = search_params
        params = {}
        selection_str = query
        if "WHERE " in query:
            selection_str = query[query.find("WHERE ") + 6 :]
            if "SCOPE " in query:
                selection_str = selection_str[: selection_str.find("SCOPE ")]
            if "WITH " in query:
                selection_str = selection_str[: selection_str.find(" WITH")]

            if "[" in selection_str:
                # parse simple selection, e.g.,
                # digital[title] AND platform[all]
                selection = re.split(" AND | OR ", selection_str)
                selection_str = " ".join(
                    [
                        f"(lower(title) LIKE '%{x.lstrip().rstrip().lower()}%' OR "
                        f"lower(abstract) LIKE '%{x.lstrip().rstrip().lower()}%')"
                        if (
                            x not in ["AND", "OR"]
                            and not any(
                                t in x
                                for t in ["url=", "venue_key", "journal_abbreviated"]
                            )
                        )
                        else x
                        for x in selection
                    ]
                )

            # else: parse complex selection (no need to parse!?)
            params["selection_clause"] = selection_str

        if "SCOPE " in query:
            # selection_str = selection_str[: selection_str.find("SCOPE ")]
            scope_part_str = query[query.find("SCOPE ") + 6 :]
            if "WITH " in query:
                scope_part_str = scope_part_str[: scope_part_str.find(" WITH")]
            params["scope"] = {}  # type: ignore
            for scope_item in scope_part_str.split(" AND "):
                key, value = scope_item.split("=")
                if "url" in key:
                    if "https://dblp.org/db/" in value:
                        params["scope"]["venue_key"] = (  # type: ignore
                            value.replace("/index.html", "")
                            .replace("https://dblp.org/db/", "")
                            .replace("url=", "")
                            .replace("'", "")
                        )
                        continue
                params["scope"][key] = value.rstrip("'").lstrip("'")  # type: ignore

        if "WITH " in query:
            scope_part_str = query[query.find("WITH ") + 5 :]
            params["params"] = {}  # type: ignore
            for scope_item in scope_part_str.split(" AND "):
                key, value = scope_item.split("=")
                params["params"][key] = value.rstrip("'").lstrip("'")  # type: ignore

        return params

    def validate_query(self, *, query: str) -> None:

        if " FROM " not in query:
            raise colrev_exceptions.InvalidQueryException('Query missing "FROM" clause')

        sources = self.parse_sources(query=query)

        scripts = []
        for source_name in sources:
            feed_config = self.get_feed_config(source_name=source_name)
            scripts.append(feed_config["search_script"])

        required_search_scripts = [
            s.search_script for s in self.review_manager.settings.sources
        ]

        AdapterManager = self.review_manager.get_environment_service(
            service_identifier="AdapterManager"
        )
        self.search_scripts = AdapterManager.load_scripts(
            PROCESS=self,
            scripts=scripts + required_search_scripts,
        )

        if len(sources) > 1:
            individual_sources = [
                k
                for k, v in self.search_scripts.items()
                if "individual" == v["endpoint"].mode
            ]
            if any(source in individual_sources for source in sources):
                violations = [
                    source for source in sources if source in individual_sources
                ]
                raise colrev_exceptions.InvalidQueryException(
                    "Multiple query sources include a source that can only be"
                    f" used individually: {violations}"
                )

        for source_name in sources:
            feed_config = self.get_feed_config(source_name=source_name)
            for source in sources:
                # TODO : parse params (which may also raise errors)
                script = self.search_scripts[feed_config["search_script"]["endpoint"]]
                script.validate_params(query=query)  # type: ignore

    def get_feed_config(self, *, source_name) -> dict:

        conversion_script = {"endpoint": "bibtex"}

        search_script = {"endpoint": "TODO"}
        if source_name == "DBLP":
            search_script = {"endpoint": "search_dblp"}
        elif source_name == "CROSSREF":
            search_script = {"endpoint": "search_crossref"}
        elif source_name == "BACKWARD_SEARCH":
            search_script = {"endpoint": "backward_search"}
        elif source_name == "COLREV_PROJECT":
            search_script = {"endpoint": "search_colrev_project"}
        elif source_name == "INDEX":
            search_script = {"endpoint": "search_local_index"}
        elif source_name == "PDFS":
            search_script = {"endpoint": "search_pdfs_dir"}

        source_identifier = "TODO"
        if search_script["endpoint"] in self.built_in_scripts:
            source_identifier = self.built_in_scripts[search_script["endpoint"]][
                "endpoint"
            ].source_identifier

        return {
            "source_identifier": source_identifier,
            "search_script": search_script,
            "conversion_script": conversion_script,
            "source_prep_scripts": [],
        }

    def add_source(self, *, query: str) -> None:

        # TODO : parse query (input format changed to sql-like string)
        # TODO : the search query/syntax translation has to be checked carefully
        # (risk of false-negative search results caused by errors/missing functionality)
        # https://lucene.apache.org/core/2_9_4/queryparsersyntax.html
        # https://github.com/netgen/query-translator/tree/master/lib/Languages/Galach
        # https://github.com/netgen/query-translator
        # https://medlinetranspose.github.io/documentation.html
        # https://sr-accelerator.com/#/help/polyglot

        # Start with basic query
        # RETRIEVE * FROM crossref,dblp WHERE digital AND platform
        # Note: corresponds to "digital[all] AND platform[all]"

        saved_args = {"add": f'"{query}"'}

        as_filename = ""
        if " AS " in query:
            as_filename = query[query.find(" AS ") + 4 :]
            as_filename = (
                as_filename.replace("'", "").replace('"', "").replace(" ", "_")
            )
            if ".bib" not in as_filename:
                as_filename = f"{as_filename}.bib"
            query = query[: query.find(" AS ")]
        query = f"SELECT * {query}"

        self.validate_query(query=query)

        # TODO : check whether url exists (dblp, project, ...)
        sources = self.parse_sources(query=query)
        if "WHERE " in query:
            selection = query[query.find("WHERE ") :]
        elif "SCOPE " in query:
            selection = query[query.find("SCOPE ") :]
        elif "WITH" in query:
            selection = query[query.find("WITH ") :]
        else:
            print("Error: missing WHERE or SCOPE clause in query")
            return

        for source_name in sources:
            duplicate_source = []
            try:
                duplicate_source = [
                    x
                    for x in self.sources
                    if source_name == x["search_parameters"][0]["endpoint"]
                    and selection == x["search_parameters"][0]["params"]
                ]
            except TypeError:
                pass

            if len(duplicate_source) > 0:
                print(
                    "Source already exists: "
                    f"RETRIEVE * FROM {source_name} {selection}\nSkipping.\n"
                )
                continue

            if as_filename != "":
                filename = as_filename
            else:
                filename = f"{source_name}.bib"
                i = 0
                # TODO : filename may not yet exist (e.g., in other search feeds)
                while filename in [x.filename for x in self.sources]:
                    i += 1
                    filename = filename[: filename.find("_query") + 6] + f"_{i}.bib"

            feed_file_path = self.review_manager.path / Path(filename)
            assert not feed_file_path.is_file()

            # The following must be in line with settings.py/SearchSource
            search_type = "DB"
            source_identifier = "TODO"

            # TODO : add "USING script_x" when we add a search_script!

            if search_type == "DB":
                feed_config = self.get_feed_config(source_name=source_name)
                source_identifier = feed_config["source_identifier"]
                search_script = feed_config["search_script"]
                conversion_script = feed_config["conversion_script"]
                source_prep_scripts = feed_config["source_prep_scripts"]
            else:
                search_script = {}
                conversion_script = {"endpoint": "bibtex"}
                source_prep_scripts = []

            # NOTE: for now, the parameters are limited to whole journals.
            add_source = colrev.settings.SearchSource(
                filename=Path(
                    f"search/{filename}",
                ),
                search_type=colrev.settings.SearchType(search_type),
                source_name=source_name,
                source_identifier=source_identifier,
                search_parameters=selection,
                search_script=search_script,
                conversion_script=conversion_script,
                source_prep_scripts=source_prep_scripts,
                comment="",
            )
            self.review_manager.p_printer.pprint(add_source)
            self.review_manager.settings.sources.append(add_source)
            self.review_manager.save_settings()

            self.review_manager.create_commit(
                msg=f"Add search source {filename}",
                script_call="colrev search",
                saved_args=saved_args,
            )

        self.main(selection_str="all")

    def remove_forthcoming(self, *, source):
        self.review_manager.logger.info("Remove forthcoming")

        with open(source.feed_file, encoding="utf8") as bibtex_file:
            records = self.review_manager.dataset.load_records_dict(
                load_str=bibtex_file.read()
            )

            record_list = records.values()
            record_list = [r for r in record_list if "forthcoming" != r.get("year", "")]
            records = {r["ID"]: r for r in record_list}

            self.review_manager.dataset.save_records_dict_to_file(
                records=records, save_path=source.feed_file
            )

    def main(self, *, selection_str: str) -> None:

        # Reload the settings because the search sources may have been updated
        self.review_manager.settings = self.review_manager.load_settings()

        # TODO : when the search_file has been filled only query the last years

        def load_automated_search_sources() -> list:

            automated_sources = [
                x for x in self.sources if "endpoint" in x.search_script
            ]

            automated_sources_selected = automated_sources
            if selection_str is not None:
                if "all" != selection_str:
                    automated_sources_selected = [
                        f
                        for f in automated_sources
                        if str(f.filename) in selection_str.split(",")
                    ]
                if len(automated_sources_selected) == 0:
                    available_options = ", ".join(
                        [str(f.filename) for f in automated_sources]
                    )
                    print(f"Error: {selection_str} not in {available_options}")
                    raise colrev_exceptions.NoSearchFeedRegistered()

            for source in automated_sources_selected:
                source.feed_file = self.review_manager.path / Path(source.filename)

            return automated_sources_selected

        for source in load_automated_search_sources():

            params = self.parse_parameters(search_params=source.search_parameters)

            print()
            self.review_manager.logger.info(
                f"Retrieve from {source.source_name}: {params}"
            )

            search_script = self.search_scripts[source.search_script["endpoint"]]
            search_script.run_search(
                search=self,
                params=params,
                feed_file=source.feed_file,
            )

            if source.feed_file.is_file():
                if not self.review_manager.settings.search.retrieve_forthcoming:
                    self.remove_forthcoming(source=source)

                self.review_manager.dataset.add_changes(path=str(source.feed_file))
                self.review_manager.create_commit(
                    msg="Run search", script_call="colrev search"
                )

    def setup_custom_script(self) -> None:

        filedata = pkgutil.get_data(__name__, "template/custom_search_script.py")
        if filedata:
            with open("custom_search_script.py", "w", encoding="utf-8") as file:
                file.write(filedata.decode("utf-8"))

        self.review_manager.dataset.add_changes(path="custom_search_script.py")

        new_source = colrev.settings.SearchSource(
            filename=Path("custom_search.bib"),
            search_type=colrev.settings.SearchType.DB,
            source_name="custom_search_script",
            source_identifier="TODO",
            search_parameters="TODO",
            search_script={"endpoint": "TODO"},
            conversion_script={"endpoint": "TODO"},
            source_prep_scripts=[{"endpoint": "TODO"}],
            comment="",
        )

        self.review_manager.settings.sources.append(new_source)
        self.review_manager.save_settings()

    def view_sources(self) -> None:

        for source in self.sources:
            self.review_manager.p_printer.pprint(source)

        print("\nOptions:")
        options = ", ".join(list(self.search_scripts.keys()))
        print(f"- endpoints: {options}")


if __name__ == "__main__":
    pass
