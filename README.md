# ![Open Chrono-Morph Viewer](ui/graphics/design/logo_text.png)

The OCMV project represents a cross-platform visualization package for
large volumetric image sets with multiple image channels and one or two
temporal axes. There is support for saving keyframes and animating
between them with the animation engine (requiring FFMPEG to convert the 
animation frames to a video file). The viewer includes a unique,
yet intuitive smooth clipping function based on thin-plate splines for 
easily and aesthetically tracking morphology as it changes over time.

Note: This software is designed for a large number of 
medium-sized volumes, with each volume being around 1 GB or less—it is
**not suitable for a very large individual volume!** Each volume must be 
small enough to fit
inside your total GPU memory; for example, if you have 8 GB of dedicated
GPU memory and 16 GB of shared GPU memory, then you can, in principle,
open an individual volume up to 24 GB. In practice, you would then be unable to
use the clipping spline at full resolution because the mask also utilizes
some of your GPU memory.

This software is under active development. If you notice any errors or 
abnormalities, we would greatly appreciate it if you went to the "Issues"
tab on this page and documented the issue so we can address it.

## Installation instructions
For Windows, Ubuntu, and macOS.

[Read here](documentation/install/installation-instructions.md)

## Tutorials & demonstrations

Some demonstration tutorials are available on YouTube showcasing several 
aspects:

1. [The two-axis timeline](https://youtu.be/ZUTMIbecfRU)
2. [The clipping spline](https://youtu.be/PlSisrJjMvc)
3. [Saving and loading scene files](https://youtu.be/SiHReuKi4po)
4. [Example animations using the Python API](https://youtu.be/HkJPfJoB_q4)

## Supported file formats

OCMV is designed to load 3D volumes, each in a separate NRRD file. The
files can either have attached headers or run in headless mode, but the
volume file must have three spatial dimensions (XYZ), with an optional
channel dimension (C) ordered from fastest to slowest as CXYZ. Image
values must be either unsigned 8-bit or 16-bit. Timing information can
be specified via custom fields in the NRRD header.

TIFF files are also supported to a limited degree. This file format was not 
originally designed to specify 3D scale information. OCMV currently only 
recognizes the metadata format used by ImageJ; other TIFF files may appear 
compressed or stretched along the Z-axis due to this missing scale information.
There may also be a performance penalty associated with reordering the voxels.

For these reasons, among others, we recommend the NRRD format. A wide 
variety of image formats can be converted to NRRD via ImageJ. We have 
developed a modified version of the ImageIO plugin to expand ImageJ's 
built-in NRRD reading and writing capabilities to 5D images with channels 
in the appropriate order for use with OCMV. This plugin is currently in the 
beta stage but may eventually be incorporated into ImageJ, if approved.
This plugin can be found at https://github.com/afaubert/IO.

## References

Please use this citation if you find our software useful in your 
research. See also for an overview of the software, including demo
videos and supplementary materials:

> Andre C. Faubert and Shang Wang, "Open Chrono-Morph viewer: visualize big
bioimage time series containing heterogeneous volumes,"
_Bioinformatics_, 41(1), 15 Jan. 2025,
[doi:10.1093/bioinformatics/btae761](https://doi.org/10.1093/bioinformatics/btae761)

Please use this citation if you use the clipping spline feature for any 
visualizations. See also for a detailed description of the 
clipping spline and some examples of its use for cardiac timeseries:

> Andre C. Faubert and Shang Wang, "Clipping spline: interactive, dynamic
4D volume clipping and analysis based on thin plate spline,"
_Biomedical Optics Express_, 16(2), 499–519, 8 Jan. 2025,
[doi:10.1364/BOE.544231](https://doi.org/10.1364/BOE.544231)

## Test dataset

A test dataset for OCMV is available on
[Zenodo](https://doi.org/10.5281/zenodo.13712866).

## License

Open Chrono-Morph Viewer, a project for visualizing volumetric time-series.
Copyright © 2024 Andre C. Faubert

This work is published under GPLv3. See [LICENSE](LICENSE) for the legal code.

## Contact

Please reach out to Andre Faubert (<afaubert@stevens.edu>) with any 
questions or comments.

## Acknowledgements

Funded by the National Institutes of Health (R35GM142953).

A special thanks to our colleagues at
[Dr. Shang Wang's Lab](https://www.shangwanglab.org/team)!
