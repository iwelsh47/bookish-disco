#!/usr/bin/env python3

import argparse
import re
import urllib.request
import logging
from typing import Optional, Tuple
from html import parser
from pathlib import Path

logging.basicConfig(level=logging.INFO, handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)


def download_file(url: str, dest: str):
    """Download a file from a URL to a destination.

    Args:
        url: The URL of the file to download.
        dest: The destination path where the file will be saved.
    """
    logger.info(f"Downloading {url} to {dest}")
    urllib.request.urlretrieve(url, dest)


class CRIndexParser(parser.HTMLParser):
    """An HTML parser to extract Critical Role transcript file links from the index.

    Attributes:
        TRANSCRIPT_RE (re.Pattern): A regular expression to match transcript file names.
    """
    TRANSCRIPT_RE = re.compile(r"^cr.+\.html$")

    def __init__(self):
        """Initialise the CRIndexParser."""
        super().__init__()
        self.in_main = False
        self.transcript_files = set()

    def handle_starttag(self, tag: str, attrs: list[Tuple[str, Optional[str]]]):
        """Handle the start of an HTML tag.

        Identifies transcript file links within the main section and adds them to the
        `self.transcript_files` set.

        Args:
            tag: The name of the tag.
            attrs: A list of (attribute, value) pairs.
        """
        if tag == "main":
            self.in_main = True
        elif tag == "a" and self.in_main:
            attr_dict = dict(attrs)
            href = attr_dict.get("href")
            if href is not None and self.TRANSCRIPT_RE.match(href):
                self.transcript_files.add(href)

    def handle_endtag(self, tag: str):
        """Handle the end of an HTML tag.

        Identifies when exiting the main section so no more files are found.

        Args:
            tag: The name of the tag.
        """

        if tag == "main":
            self.in_main = False

    def feed(self, data):
        logger.info("Parsing index.html for transcript files...")
        return super().feed(data)


class CRTranscriptParser(parser.HTMLParser):
    """An HTML parser specifically for parsing CR Transcripts."""

    def __init__(self):
        """Initialise the CRTranscriptParser."""
        super().__init__()
        self.in_lines = False
        self.lines = []
        self.process = None

    def handle_starttag(self, tag: str, attrs: list[Tuple[str, Optional[str]]]):
        """Handle the start of an HTML tag.

        Only processes tags relevant to transcript lines: tags containg speaker names
        and dialogue text.

        Args:
            tag: The name of the tag.
            attrs: A list of (attribute, value) pairs.
        """
        if tag == "div" and ("id", "lines") in attrs:
            self.in_lines = True
        elif tag == "strong" and self.in_lines:
            self.process = "name"
        elif tag == "dd" and self.in_lines:
            self.process = "text"

    def handle_data(self, data: str):
        """Handle data within HTML tags.

        Processes data based on the current tag being processed (speaker name or
        dialogue text).

        Args:
            data: The data within the HTML tag.
        """
        if self.process:
            if self.process == "name":
                self.lines.append({"name": data.strip()})
            elif self.process == "text":
                cur_dat = self.lines[-1] if self.lines else {}
                # Sometimes text is split across multiple tags for the same speaker,
                # so combine these
                if 'text' in cur_dat.keys():
                    cur_dat['text'] = f'{cur_dat["text"]} {data.strip()}'
                else:
                    cur_dat["text"] = data.strip()
            else:
                pass  # Unknown process type
        self.process = None


def main():
    URL_ROOT = "https://www.kryogenix.org/crsearch/html"
    parser = argparse.ArgumentParser(
        description="Collect and parse Critical Role transcript files"
    )
    parser.add_argument("-u", "--update",
                        help="Update any transcripts that are available online",
                        action="store_true")
    parser.add_argument("-d", "--data-dir",
                        help="Directory to store transcript data",
                        default=Path("data/raw/cr_transcripts/"),
                        type=Path)
    parser.add_argument("-o", "--output-dir",
                        help="Directory to store processed transcript data",
                        default=Path("data/processed/cr_transcripts/"),
                        type=Path)
    parser.add_argument("--exclude-names",
                        help="Include speaker names in output",
                        action="store_false", dest="include_names")
    args = parser.parse_args()

    if args.update:
        index_file = args.data_dir/"index.html"
        logger.info("Updating transcripts...")
        download_file(f"{URL_ROOT}/index.html", index_file)

        with open(index_file, "r") as f:
            index = CRIndexParser()
            index.feed(f.read())
            available_files = index.transcript_files

        present_files = {f.name for f in args.data_dir.glob("cr*.html")}
        to_download = available_files - present_files
        logger.info(f"Found {len(to_download)} new transcripts to download.")
        for filename in to_download:
            download_file(f"{URL_ROOT}/{filename}", args.data_dir/filename)
        logger.info("Transcript update complete.")

    all_files = args.data_dir.glob("cr*.html")
    for filepath in all_files:
        logger.info(f"Processing {filepath.name}...")
        with open(filepath, "r") as f:
            parser = CRTranscriptParser()
            parser.feed(f.read())
            output_path = args.output_dir/(filepath.stem + ".md")
            with open(output_path, "w") as out_f:
                for line in parser.lines:
                    if args.include_names and "name" in line:
                        out_f.write(f"**{line['name']}**: ")
                    if "text" in line:
                        out_f.write(f"{line['text']}\n")
        logger.info(f"Processed data saved to {output_path}")


if __name__ == "__main__":
    main()
