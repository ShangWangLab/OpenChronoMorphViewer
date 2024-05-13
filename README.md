# Open Chrono-Morph Viewer (OCMV)

This project represents a cross-platform visualization package for large
3D, 4D, and 5D data sets with multiple image channels. There is support
for saving keyframes and animating between them with the animation engine
(requires FFMPEG to convert the animation frames to a video file). The
viewer also includes a unique, yet intuitive smooth clipping function
based on thin-plate splines for easily and aesthetically tracking
morphology as it changes over time.

This project may be a good fit if you need to:
- Look through thousands of 3D volumes with minimal overhead.
- Use an inspectable file format that is easy to look at and understand (unlike DICOM).
- View complex internal anatomy that cannot be exposed with a combination of simple planar cuts.
- Make attractive visualizations of morphological development.
- Save money with a free package.
- Use a low-end computer.

This project may not be a good fit if you need to:
- View extremely large volumes that do not fit into RAM.
- Perform real-time data operations while visualizing.

## Supported Platforms

- Windows 10/11
- Ubuntu 20.04+
- macOS 13.0+ (experienced issues on version 10.9)

## Dependencies

Required software:
- [Python](https://www.python.org/downloads) version 3.11.4
- [FFMPEG](https://ffmpeg.org/download.html) version 6.1.1 (only required for animating videos)

Required 3rd party Python packages:
- NumPy 1.25.2 for 3D data operations
- PSutil 5.9.5 for getting the current RAM usage
- PyNRRD 1.0.0 for the image file format (Nearly Raw Raster Data)
- PyQt5 5.15.2.2.3 for the user interface
- SciPy 1.11.1 for the "cdist" function
- PyVTK 9.2.6 for volumetric rendering

See [dependency-install-Windows.bat](dependency-install-Windows.bat) for an example of the command to install all the Python dependencies.

## Supported file formats

OCMV is designed to load 3D volumes, each in a separate NRRD file. The files can either have attached headers or run in headless mode, but the volume file must have three spatial dimensions (XYZ), with an optional channel dimension (C) ordered from fastest to slowest as CXYZ. Image values must be either unsigned 8-bit or 16-bit. Timing information can be specified via custom fields in the NRRD header.

## License

Open Chrono-Morph Viewer, a project for visualizing volumetric time-series.
Copyright © 2024 Andre C. Faubert

This work is published under GPLv3. See [LICENSE](LICENSE) for the legal code.

## Contact

Please reach out to Andre Faubert (<afaubert@stevens.edu>) with any questions or comments.

## Acknowledgements

Funded by the National Institutes of Health (R35GM142953).

A special thanks to our colleagues at [Dr. Shang Wang's Biophotonic's Lab](https://www.shangwanglab.org/team)!