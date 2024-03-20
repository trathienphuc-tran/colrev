#! /usr/bin/env python
"""OCR as a PDF preparation operation"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import docker
import zope.interface
from dataclasses_jsonschema import JsonSchemaMixin

import colrev.env.package_manager
import colrev.env.utils
import colrev.record
from colrev.constants import Fields
from colrev.constants import Filepaths
from colrev.constants import PDFDefectCodes


# pylint: disable=too-few-public-methods
# pylint: disable=duplicate-code


@zope.interface.implementer(colrev.env.package_manager.PDFPrepPackageEndpointInterface)
@dataclass
class OCRMyPDF(JsonSchemaMixin):
    """Prepare PDFs by applying OCR based on OCRmyPDF"""

    settings_class = colrev.env.package_manager.DefaultSettings
    ci_supported: bool = False

    def __init__(
        self,
        *,
        pdf_prep_operation: colrev.ops.pdf_prep.PDFPrep,
        settings: dict,
    ) -> None:
        self.settings = self.settings_class.load_settings(data=settings)
        self.review_manager = pdf_prep_operation.review_manager

        if not self.review_manager.in_ci_environment():
            self.ocrmypdf_image = "jbarlow83/ocrmypdf:latest"
            self.review_manager.environment_manager.build_docker_image(
                imagename=self.ocrmypdf_image
            )

    def _apply_ocr(
        self,
        *,
        record: colrev.record_pdf.PDFRecord,
    ) -> colrev.record_pdf.PDFRecord:
        pdf_path = self.review_manager.path / Path(record.data[Fields.FILE])
        non_ocred_filename = Path(str(pdf_path).replace(".pdf", "_no_ocr.pdf"))
        pdf_path.rename(non_ocred_filename)
        orig_path = (
            pdf_path.parents[0]
            if pdf_path.is_file()
            else self.review_manager.get_path(Filepaths.PDF_DIR)
        )

        # options = ""
        # if rotate:
        #     options = options + '--rotate-pages '
        # if deskew:
        #     options = options + '--deskew '
        docker_home_path = Path("/home/docker")

        args = (
            f"--force-ocr --jobs 4 -l eng {str(docker_home_path / non_ocred_filename.name)} "
            f"{str(docker_home_path / pdf_path.name)}"
        )

        client = docker.from_env(timeout=120)
        client.containers.run(
            image=self.ocrmypdf_image,
            command=args,
            auto_remove=True,
            user=f"{os.geteuid()}:{os.getegid()}",
            volumes=[f"{orig_path}:/home/docker"],
        )

        record.add_data_provenance_note(
            key=Fields.FILE, note="pdf_processed with OCRMYPDF"
        )
        record.set_text_from_pdf()
        return record

    def prep_pdf(
        self,
        record: colrev.record_pdf.PDFRecord,
        pad: int,  # pylint: disable=unused-argument
    ) -> dict:
        """Prepare the PDF by applying OCR"""

        if (
            Fields.FILE not in record.data
            or not record.data[Fields.FILE].endswith(".pdf")
            or PDFDefectCodes.NO_TEXT_IN_PDF not in record.defects("file")
        ):
            return record.data

        self.review_manager.report_logger.info(f"apply_ocr({record.data[Fields.ID]})")
        record = self._apply_ocr(record=record)

        return record.data
