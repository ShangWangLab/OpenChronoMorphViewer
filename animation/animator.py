import os
from typing import Callable, Optional

from animation.aframe import AFrame
from animation.aframespan import AFrameSpan
from animation.amainscene import AMainScene
from animation.aview import AView
from animation.errorreportlogger import ErrorReportLogger
from timeline import Timeline
from volumeimage import VolumeImage


class Animator:
    def __init__(self, frame_rate: float, dir_out_path: str, preview: bool = True) -> None:
        # The frame rate (FPS) of the output video.
        self.frame_rate = frame_rate  # Frames/sec
        # The directory to put the rendered frame images.
        self.dir_out_path: str = dir_out_path
        self.a_frames: list[AFrame] = []
        self.preview: bool = preview
        # noinspection PyTypeChecker
        self.timeline = Timeline(ErrorReportLogger, 0)

    def set_volume_dir(self, dir_path: str) -> None:
        """TODO"""

        self.set_volume_files(dir_volumes(dir_path))

    def set_volume_files(self, volume_paths: list[str]) -> None:
        """TODO"""

        # TODO: Add a progress reporter callback.
        self.timeline.set_file_paths(volume_paths)

    def make_frames(
            self,
            inclusion_criteria: Optional[Callable[[VolumeImage], bool]] = None,
            volume_rate: float = 1,
            absolute_rate: bool = False) -> AFrameSpan:
        """Produce a span of frames at the render frame rate, each with an associated volume.

        When "absolute_rate" is True, "volume_rate" is specified directly as
        volumes/sec, otherwise it is relative to the period specified by the
        volumes themselves.

        "absolute_rate" as True may behave unstably when both:
        1. The acquisition period varies, and
        2. The final volume rate is greater than the rendering frame rate.
        The resulting frame skips can cause some of the volume periods to be
        ignored.
        """

        volumes: list[VolumeImage] = self.timeline.volumes
        if inclusion_criteria is not None:
            volumes: list[VolumeImage] = list(filter(inclusion_criteria, volumes))
        assert len(volumes) > 0, "Volume list is empty."

        a_frames: list[AFrame] = []
        i: float = 0.
        ii: int = 0
        if absolute_rate:
            inc: float = volume_rate/self.frame_rate
            while ii < len(volumes):
                a_frames.append(AFrame(volumes[ii]))
                i += inc
                ii = int(i)
        else:
            while ii < len(volumes):
                vol: VolumeImage = volumes[ii]
                a_frames.append(AFrame(vol))
                i += volume_rate / (vol.period*self.frame_rate)
                ii = int(i)
        return AFrameSpan(a_frames)

    def add_frames(self, a_frames: AFrameSpan or AFrame) -> None:
        """TODO"""

        if type(a_frames) == AFrame:
            self.a_frames.append(a_frames.copy())
        else:
            for a_frame in a_frames.a_frames:
                self.a_frames.append(a_frame.copy())

    def render_frames(self, frame_size: tuple[int, int], start_frame: int = 0) -> None:
        """Ask each animation frame to render itself to the output directory.

        You can change "start_frame" to resume a previous rendering starting from
        the frame index specified.
        """

        if not os.path.exists(self.dir_out_path):
            os.mkdir(self.dir_out_path)

        print(f"Making the render window (size {frame_size} requested)...")
        magnification = 1
        #max_dim = max(frame_size)
        #magnification: int = math.ceil(max_dim / 1000)
        #frame_size = (frame_size[0] // magnification, frame_size[1] // magnification)
        #print(f"Actually size {frame_size} with magnification of {magnification}x.")

        view: AView = AView(frame_size, magnification=magnification, show=self.preview)
        print("Made the render window.")

        print("Making Scene...")
        scene = AMainScene(view, self.timeline)
        print("Initialized the scene.")

        n = len(self.a_frames)
        for i, a_frame in enumerate(self.a_frames, start=start_frame):
            print(f"Processing frame {i+1}/{n}...")
            path_out = os.path.join(self.dir_out_path, f"frame{i:06d}.png")
            a_frame.render(view, scene, path_out)
        view.close()

    def compile_video(self, video_path: str, compression_level: int = 23, h265: bool = False) -> None:
        """Use FFMPEG to convert the frame images rendered to a video file."""

        if os.path.isfile(video_path):
            os.remove(video_path)
            assert not os.path.exists(video_path), f"Can't overwrite the video at '{video_path}'."

        command = " ".join([
            "ffmpeg",
            f"-r {self.frame_rate:f}",
            f"-start_number 0",
            f'-i "{self.dir_out_path}/frame%06d.png"',
            f"-vframes {len(self.a_frames)}",
            "-c:v libx26" + ("5" if h265 else "4"),
            f"-crf {compression_level}",
            "-vf format=yuv420p",
            f'"{video_path}"'
        ])

        print(command)
        status: int = os.system(command)
        assert status == 0, "Video conversion failed."


def name_is_nrrd(name: str) -> bool:
    """Determine if the file name is that of an NRRD file."""

    lower = name.lower()
    return lower.endswith(".nrrd") or lower.endswith(".nhdr")


def dir_volumes(dir_path: str) -> list[str]:
    """Get the names of all NRRD files in a given directory."""

    file_names = os.listdir(dir_path)
    return [os.path.join(dir_path, n) for n in file_names if name_is_nrrd(n)]
