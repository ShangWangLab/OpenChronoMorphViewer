#!/usr/bin/python3.11

"""A command line utility for converting a directory of 2D images to a set of
headless NRRD volumes and their corresponding raw files.

Usage:
    python3.11 tiff2nrrd.py <directory of image files> <directory of NHDR files>

Formats for file names:
    Input: name_Ssss_Tttt_Ccc.tif
    Output: Sssss_Ttttt.nhdr and Sssss_Ttttt.raw
"""

#  Open Chrono-Morph Viewer, a project for visualizing volumetric time-series.
#  Copyright © 2024 Andre C. Faubert
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

import asyncio
import argparse
import io
import os
import re

import aiofiles
import numpy as np
import nrrd
from PIL import Image


class ImageRef:
    series_pat = re.compile(r"[Ss](\d+)")
    time_pat = re.compile(r"[Tt](\d+)")
    z_pat = re.compile(r"[Zz](\d+)")
    channel_pat = re.compile(r"[Cc](\d+)")

    def __init__(self, file_name: str):
        self.file_name: str = file_name
        self.is_valid: bool = False

        if not self.is_image_file():
            return

        sm = ImageRef.series_pat.search(file_name)
        if not sm:
            return
        try:
            self.s: int = int(sm.groups()[0])
        except ValueError:
            return

        tm = ImageRef.time_pat.search(file_name)
        if not tm:
            return
        try:
            self.t: int = int(tm.groups()[0])
        except ValueError:
            return

        zm = ImageRef.z_pat.search(file_name)
        if not zm:
            return
        try:
            self.z: int = int(zm.groups()[0])
        except ValueError:
            return

        cm = ImageRef.channel_pat.search(file_name)
        if not cm:
            return
        try:
            self.c: int = int(cm.groups()[0])
        except ValueError:
            return

        self.is_valid = True

    def is_image_file(self) -> bool:
        fn = self.file_name.lower()
        return (fn.endswith(".png")
                or fn.endswith(".jpg")
                or fn.endswith(".jpeg")
                or fn.endswith(".tif")
                or fn.endswith(".tiff"))

    def load(self, dir_path: str) -> np.ndarray:
        # noinspection PyTypeChecker
        return np.array(
            Image.open(os.path.join(dir_path, self.file_name)),
            np.uint8)

    async def load_async(self, dir_path: str) -> np.ndarray:
        path = os.path.join(dir_path, self.file_name)
        async with aiofiles.open(path, mode="rb") as f:
            file_data = await f.read()
        # noinspection PyTypeChecker
        return np.array(Image.open(io.BytesIO(file_data)), np.uint8)


def split_series(files: list[str]) -> dict[int, list[ImageRef]]:
    series = dict()
    for file in files:
        im_ref = ImageRef(file)
        if not im_ref.is_valid:
            continue
        if im_ref.s in series:
            series[im_ref.s].append(im_ref)
        else:
            series[im_ref.s] = [im_ref]
    return series


async def load_images(dir_in: str, im_refs: list[ImageRef]):
    return await asyncio.gather(*(r.load_async(dir_in) for r in im_refs))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="NHDR Convert",
        description="Convert image files to NHDR format.")

    # Required arguments
    parser.add_argument(
        "input_directory", type=str, help="Input directory containing image files")
    parser.add_argument(
        "output_directory", type=str, help="Output directory for converted files")

    args = parser.parse_args()
    dir_in = args.input_directory
    dir_out = args.output_directory

    if not os.path.isdir(dir_in):
        print("Input directory does not exist.")
        return
    if not os.path.isdir(dir_out):
        try:
            os.mkdir(dir_out)
        except OSError:
            print("Failed to create the output directory.")
            return

    files = os.listdir(dir_in)
    series = split_series(files)

    for s, s_refs in series.items():
        t0 = min(r.t for r in s_refs)
        t1 = max(r.t for r in s_refs)
        nt = t1 - t0 + 1
        t_refs = [[] for t in range(nt)]
        for r in s_refs:
            t_refs[r.t - t0].append(r)
        for t, refs in enumerate(t_refs):
            z0 = min(r.z for r in refs)
            z1 = max(r.z for r in refs)
            nz = z1 - z0 + 1
            c0 = min(r.c for r in refs)
            c1 = max(r.c for r in refs)
            nc = c1 - c0 + 1

            image_arrays = asyncio.run(load_images(dir_in, refs))
            w, h = image_arrays[0].shape
            volume = np.empty((nz, h, w, nc), np.uint8)
            for r, a in zip(refs, image_arrays):
                volume[r.z - z0, :, :, r.c - c0] = a

            out_file_path = os.path.join(dir_out, f"S{s:04d}_T{t:04d}.nhdr")
            header = {
                "encoding": "raw",
                "time index": t,
                "scan index": s,
                "n times": t1 - t0,
                "space directions": [
                    (1, 0, 0),
                    (0, 1, 0),
                    (0, 0, 1)],
                "space origin": [0, 0, 0],
                "space units": ["microns", "microns", "microns"],
                "labels": ["channel", "x", "y", "z"]
            }
            nrrd.write(out_file_path, data=volume, header=header,
                       detached_header=True, index_order="C")


if __name__ == "__main__":
    main()
