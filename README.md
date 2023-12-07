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

## Dependencies

Developed for Python version 3.10.10.

Required 3rd party packages:
- NumPy 1.23.5 for 3D data operations
- PyNRRD 1.0.0 (Nearly Raw Raster Data) for the image file format
- PyQt5 for the user interface
- SciPy 1.10.1 for the cdist function
- VTK 9.2.6 for volumetric rendering

See [dependency-install.bat](dependency-install.bat) for an example of the command to install all the dependencies.

## License

See the [LICENSE](LICENSE) for more information.

## Contact

Please reach out to Andre Faubert (<afaubert@stevens.edu>) with any questions or comments.

## Acknowledgements

Funded by the National Institutes of Health (R01HD096335, R35GM142953).

A special thanks to our colleagues at [Dr. Shang Wang's Biophotonic's Lab]
(https://www.shangwanglab.org/team)!