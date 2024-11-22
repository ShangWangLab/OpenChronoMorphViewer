# ![Open Chrono-Morph Viewer](ui/graphics/design/logo_text.png)

The OCMV project represents a cross-platform visualization package for
large volumetric image sets with multiple image channels and one or two
temporal axes. There is support for saving keyframes and animating
between them with the animation engine (requiring FFMPEG to convert the 
animation frames to a video file). The viewer also includes a unique,
yet intuitive smooth clipping function based on thin-plate splines for 
easily and aesthetically tracking morphology as it changes over time.

Detailed installation instructions, demonstration videos, and
instructions for use will be available in the manuscript, which will be
linked here once published.

## Installation instructions
[Read here](documentation/install/installation-instructions.md)

## Supported file formats

OCMV is designed to load 3D volumes, each in a separate NRRD file. The files can either have attached headers or run in headless mode, but the volume file must have three spatial dimensions (XYZ), with an optional channel dimension (C) ordered from fastest to slowest as CXYZ. Image values must be either unsigned 8-bit or 16-bit. Timing information can be specified via custom fields in the NRRD header.

## Test dataset

A test dataset for OCMV is available on [Zenodo](https://doi.org/10.5281/zenodo.13712866).

## License

Open Chrono-Morph Viewer, a project for visualizing volumetric time-series.
Copyright © 2024 Andre C. Faubert

This work is published under GPLv3. See [LICENSE](LICENSE) for the legal code.

## Contact

Please reach out to Andre Faubert (<afaubert@stevens.edu>) with any questions or comments.

## Acknowledgements

Funded by the National Institutes of Health (R35GM142953).

A special thanks to our colleagues at
[Dr. Shang Wang's Biophotonic's Lab](https://www.shangwanglab.org/team)!
