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

import copy
from typing import Optional

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist
from tps import ThinPlateSpline
from vtkmodules.vtkRenderingCore import (
    vtkCameraInterpolator,
    vtkCamera,
)

from animation.aframe import AFrame
from animation.ascene import AScene
from animation.asceneitems.acamera import (
    vtk_camera_from_struct,
    vtk_camera_to_struct,
)
from animation.asceneitems.acontrolpoint import cp_origin_to_struct
from animation.splines import CylinderSpline
from main.volumeimage import VolumeImage


class AFrameSpan:
    """A list of animation frames with options for applying scenes."""

    def __init__(self, a_frames: Optional[list[AFrame]] = None) -> None:
        if a_frames is None:
            a_frames = []
        self.a_frames: list[AFrame] = a_frames

    def __len__(self) -> int:
        """The number of animation frames contained."""

        return len(self.a_frames)

    def __add__(self, x: "AFrameSpan") -> "AFrameSpan":
        """Concatenate the right side to the end of the left side, making copies of both."""

        return AFrameSpan(self.copy().a_frames + x.copy().a_frames)

    def __mul__(self, n: int) -> "AFrameSpan":
        """Repeat this span n times."""

        a_frames: list[AFrame] = []
        for i in range(n):
            a_frames.extend(self.copy().a_frames)
        return AFrameSpan(a_frames)

    def __getitem__(self, item: int or slice) -> "AFrameSpan" or AFrame:
        """Index into the underlying animation frame list."""

        val: AFrame or list[AFrame] = self.a_frames[item]
        if type(val) == AFrame:
            return val
        return AFrameSpan(val)

    def copy(self) -> "AFrameSpan":
        """Make a copy that can be modified without changing the underlying animation frames."""

        return AFrameSpan([x.copy() for x in self.a_frames])

    def subspan(self, low: float, high: float) -> "AFrameSpan":
        """Index into this span as a fraction of the range.

        :param low: The lower bounding fraction. Must be in range [0, 1] and under 'high'.
        :param high: The upper bounding fraction. Must be in range [0, 1] and exceed 'low'.
        :return: The subspan produced, which references the original animation frames.
        """

        assert 0 <= low <= high, "Lower bound is invalid."
        assert low <= high <= 1, "Upper bound is invalid."

        return AFrameSpan(self.a_frames[int(low*len(self)):int(high*len(self))])

    def apply_scene(self, scene: AScene) -> None:
        """Apply a scene to all animation frames contained."""

        for a_frame in self.a_frames:
            a_frame.apply_scene(scene)

    def get_optimal_scale(self, frame_height_px: int) -> float:
        """The ideal scale is the one where the minimum scale of all volumes
        maps to one pixel width on the rendered frame."""

        all_scales = np.array([f.volume.scale for f in self.a_frames])
        # noinspection PyArgumentList
        micron_per_px = float(np.min(all_scales, axis=0).min())

        # Scale is half the viewport height in microns.
        return micron_per_px * frame_height_px / 2

    def interpolate_camera_1d(
            self,
            parameters: list[float],
            keyframes: list[AScene],
            group_const: bool = False):
        """Interpolate the cameras passed and apply them to the animation frames.

        The interpolation is spline-based, using the default VTK camera interpolator,
        and has 1st order continuity with the beginning and ending states.

        :param parameters: Represents the fraction of the interpolation at which
            each keyframe occurs. A value of 0 corresponds to the first animation
            frame, while a value of 1 corresponds to the last frame (or group,
            in the case of group_const=True).
        :param keyframes: The list of scenes to interpolate cameras between.
        :param group_const: When true, interpolations goes from group to
            group, ignoring the cycles in between.
        """

        assert len(self) > 1, \
            "The frame span must contain at least two frames to assign interpolated values."
        assert len(keyframes) >= 2, "Must have at least two keyframes to interpolate."
        assert len(parameters) == len(keyframes), \
            f"{len(parameters)} interpolation parameters does not match {len(keyframes)} keyframes."

        model = vtkCameraInterpolator()
        model.SetInterpolationTypeToSpline()
        errors: list[str] = []
        for i in range(len(parameters)):
            camera = vtkCamera()
            vtk_camera_from_struct(camera, keyframes[i].items["Camera"], errors)
            assert len(errors) == 0, "Couldn't load a camera for interpolation."
            model.AddCamera(parameters[i], camera)

        orthographic_mode: bool = keyframes[0].items["Camera"]["orthographic"]
        if group_const:
            t0 = min(f.volume.group_index for f in self.a_frames)
            t1 = max(f.volume.group_index for f in self.a_frames)
        else:
            t0 = 0
            t1 = len(self.a_frames) - 1
        for i, frame in enumerate(self.a_frames):
            if group_const:
                t = (frame.volume.group_index - t0) / (t1 - t0)
            else:
                t = i / t1
            camera = vtkCamera()
            camera.SetParallelProjection(orthographic_mode)
            model.InterpolateCamera(t, camera)
            frame.scene.items["Camera"] = vtk_camera_to_struct(camera)

    def interpolate_channels_1d(
            self,
            parameters: list[float],
            keyframes: list[AScene],
            group_const: bool = False,
            spline: bool = True,
            end_continuity: int = 0) -> None:
        """Interpolate the channels passed and apply them to the animation frames.

        :param parameters: Represents the fraction of the interpolation at which
            each keyframe occurs. A value of 0 corresponds to the first animation
            frame, while a value of 1 corresponds to the last frame (or group,
            in the case of group_const=True).
        :param keyframes: The list of scenes to interpolate channel values between.
        :param group_const: When true, interpolations goes from group to
            group, ignoring the cycles in between.
        :param spline: When true, use a spline for interpolation, otherwise, use
            piecewise linear interpolation.
        :param end_continuity: The degree of continuity to enforce between the
            ends and the baseline. Setting this parameter to a 1 or 2 makes
            splines tend to level out at the ends.
        """

        n_kf = len(keyframes)
        assert len(self) > 1, \
            "The frame span must contain at least two frames to assign interpolated values."
        assert n_kf >= 2, "Must have at least two keyframes to interpolate."
        assert len(parameters) == n_kf, \
            f"{len(parameters)} interpolation parameters does not match {n_kf} keyframes."
        assert end_continuity == 0 or spline, "End continuity can only be specified for splines."
        assert 0 <= end_continuity <= 2, "End continuity degree must be in range [0, 2]."

        # The keyframes must have monotonically increasing parameters for both
        # piecewise interpolation and spline end continuity.
        i_sort = sorted(range(n_kf), key=lambda i: parameters[i])
        parameters = [parameters[i] for i in i_sort]
        keyframes = [keyframes[i] for i in i_sort]

        if spline:
            # Shallow copy so we can insert items; deep is not necessary because we don't edit the scenes.
            parameters = copy.copy(parameters)
            keyframes = copy.copy(keyframes)
            epsilon = 1e-6
            for i in range(end_continuity):
                parameters.insert(i + 1, parameters[i] + epsilon)
                keyframes.insert(i + 1, keyframes[i])
                j = len(parameters) - 1 - i
                parameters.insert(j, parameters[j] - epsilon)
                keyframes.insert(j, keyframes[j])

            # TODO: Implement this generally, not just for the special case that I need at this particular
            #  moment...
            X_fit = np.empty((n_kf, 1), np.float64)
            Y_fit = np.empty((n_kf, 2), np.float64)
            for i, kf in enumerate(keyframes):
                X_fit[i] = i / (n_kf - 1)
                Y_fit[i, :] = kf.image_channels[0]["dynamic_range"]

            spline = ThinPlateSpline(0)
            spline.fit(X_fit, Y_fit)

            X_out = np.linspace(0, 1, len(self)).reshape((len(self), 1))
            Y_out = spline.transform(X_out)
            for i, f in enumerate(self.a_frames):
                f.scene.image_channels[0]["dynamic_range"] = [float(a) for a in Y_out[i, :]]

        else:
            # TODO: Implement.
            pass

    def interpolate_planes_1d(
            self,
            parameters: list[float],
            keyframes: list[AScene],
            group_const: bool = False,
            spline: bool = True,
            end_continuity: int = 0) -> None:
        """Interpolate the clipping planes passed and apply them to the animation frames.

        :param parameters: Represents the fraction of the interpolation at which
            each keyframe occurs. A value of 0 corresponds to the first animation
            frame, while a value of 1 corresponds to the last frame (or group,
            in the case of group_const=True).
        :param keyframes: The list of scenes to interpolate planes between.
        :param group_const: When true, interpolations goes from group to
            group, ignoring the cycles in between.
        :param spline: When true, use a spline for interpolation, otherwise, use
            piecewise linear interpolation.
        :param end_continuity: The degree of continuity to enforce between the
            ends and the baseline. Setting this parameter to a 1 or 2 makes
            splines tend to level out at the ends.
        """

        n_kf = len(keyframes)
        assert len(self) > 1, \
            "The frame span must contain at least two frames to assign interpolated values."
        assert n_kf >= 2, "Must have at least two keyframes to interpolate."
        assert len(parameters) == n_kf, \
            f"{len(parameters)} interpolation parameters does not match {n_kf} keyframes."
        assert end_continuity == 0 or spline, "End continuity can only be specified for splines."
        assert 0 <= end_continuity <= 2, "End continuity degree must be in range [0, 2]."

        # The keyframes must have monotonically increasing parameters for both
        # piecewise interpolation and spline end continuity.
        i_sort = sorted(range(n_kf), key=lambda i: parameters[i])
        parameters = [parameters[i] for i in i_sort]
        keyframes = [keyframes[i] for i in i_sort]

        if spline:
            # Shallow copy so we can insert items; deep is not necessary because we don't edit the scenes.
            parameters = copy.copy(parameters)
            keyframes = copy.copy(keyframes)
            epsilon = 1e-6
            for i in range(end_continuity):
                parameters.insert(i + 1, parameters[i] + epsilon)
                keyframes.insert(i + 1, keyframes[i])
                j = len(parameters) - 1 - i
                parameters.insert(j, parameters[j] - epsilon)
                keyframes.insert(j, keyframes[j])
            n_kf = len(keyframes)

            # TODO: Implement this generally, not just for the special case that I need at this particular
            #  moment...
            X_fit = np.empty((n_kf, 1), np.float64)
            Y_fit = np.empty((n_kf, 6), np.float64)
            for i, kf in enumerate(keyframes):
                X_fit[i] = i / (n_kf - 1)
                Y_fit[i, :3] = kf.clipping_planes[0]["origin"]
                Y_fit[i, 3:] = kf.clipping_planes[0]["normal"]

            spline = ThinPlateSpline(0)
            spline.fit(X_fit, Y_fit)

            X_out = np.linspace(0, 1, len(self)).reshape((len(self), 1))
            Y_out = spline.transform(X_out)
            for i, f in enumerate(self.a_frames):
                f.scene.clipping_planes[0] = copy.deepcopy(keyframes[0].clipping_planes[0])
                f.scene.clipping_planes[0]["origin"] = [float(a) for a in Y_out[i, :3]]
                f.scene.clipping_planes[0]["normal"] = [float(a) for a in Y_out[i, 3:]]

        else:
            # TODO: Implement.
            pass

    def interpolate_cp_1d(
            self,
            parameters: list[float],
            keyframes: list[AScene],
            group_const: bool = False,
            spline: bool = True,
            smoothness: float = 0,
            end_continuity: int = 0) -> None:
        """Interpolate the control points passed and apply them to the animation
        frames.

        TODO: Missing spline functionality and missing respect for the group_const
            parameter, along with proper integration of end_continuity.

        :param parameters: Represents the fraction of the interpolation at which
            each keyframe occurs. A value of 0 corresponds to the first animation
            frame, while a value of 1 corresponds to the last frame (or group,
            in the case of group_const=True).
        :param keyframes: The list of scenes to interpolate control points between.
        :param group_const: When true, interpolations goes from group to
            group, ignoring the cycles in between.
        :param spline: When true, use a spline for interpolation, otherwise, use
            piecewise linear interpolation.
        :param end_continuity: The degree of continuity to enforce between the
            ends and the baseline. Setting this parameter to a 1 or 2 makes
            splines tend to level out at the ends.
        """

        n_kf = len(keyframes)
        assert len(self) > 1, \
            "The frame span must contain at least two frames to assign interpolated values."
        assert n_kf >= 2, "Must have at least two keyframes to interpolate."
        assert len(parameters) == n_kf, \
            f"{len(parameters)} interpolation parameters does not match {n_kf} keyframes."
        assert end_continuity == 0 or spline, "End continuity can only be specified for splines."
        assert 0 <= end_continuity <= 2, "End continuity degree must be in range [0, 2]."

        # The keyframes must have monotonically increasing parameters for
        # efficient piecewise interpolation and assignment.
        i_sort = sorted(range(n_kf), key=lambda i: parameters[i])
        parameters = [parameters[i] for i in i_sort]
        keyframes = [keyframes[i] for i in i_sort]

        scene = AScene(copy.deepcopy(keyframes[0].to_struct()))
        kf_origins = [
            np.array([
                cp["origin"]
                for cp in kf.control_points])
            for kf in keyframes
        ]
        assignments = [
            _assign_unbalanced(kf_origins[i], kf_origins[i + 1])
            for i in range(n_kf - 1)
        ]

        if spline:
            assert len(keyframes) == 2 or all(len(keyframes[0].control_points) == len(k.control_points) for
                                              k in keyframes), ""
            # Shallow copy so we can insert items; deep is not necessary because we don't edit the scenes.
            parameters = copy.copy(parameters)
            keyframes = copy.copy(keyframes)
            epsilon = 1e-6
            for i in range(end_continuity):
                parameters.insert(i + 1, parameters[i] + epsilon)
                keyframes.insert(i + 1, keyframes[i])
                j = len(parameters) - 1 - i
                parameters.insert(j, parameters[j] - epsilon)
                keyframes.insert(j, keyframes[j])

        else:
            # Piecewise linear interpolation.
            # Iterate over each line segment and figure out which frames it applies to.
            n_frames = len(self)
            for ip in range(n_kf - 1):
                a = assignments[ip]
                n_cp = a.shape[0]
                origins0 = kf_origins[ip][a[:, 0], :]
                origins1 = kf_origins[ip + 1][a[:, 1], :]
                # Points are shown or hidden according to the state of the
                # following keyframe.
                show_origins: list[bool] = [
                    keyframes[ip + 1].control_points[a[i, 1]]["checked"]
                    for i in range(n_cp)
                ]
                p0 = parameters[ip]
                p1 = parameters[ip + 1]
                i0 = min(max(0, round(p0 * n_frames)), n_frames)
                i1 = min(max(i0, round(p1 * n_frames)), n_frames)
                for i in range(i0, i1):
                    t = (i / (n_frames - 1) - p0) / (p1 - p0)
                    # The points cannot be allowed to occupy the exact same location.
                    if abs(t) < 1e-12:
                        self.a_frames[i].scene.control_points = copy.deepcopy(
                            keyframes[ip].control_points)
                    elif abs(t - 1) < 1e-12:
                        self.a_frames[i].scene.control_points = copy.deepcopy(
                            keyframes[ip + 1].control_points)
                    else:
                        out_origins = (1 - t) * origins0 + t * origins1
                        self.a_frames[i].scene.control_points = [
                            cp_origin_to_struct(out_origins[j, :], show_origin=show_origins[j])
                            for j in range(n_cp)
                        ]


    # def cp_interp(self, frames, scene0, scene1):
    #     scene = AScene(copy.deepcopy(scene0.to_struct()))
    #     n = len(frames)
    #     for i in range(n):
    #         t = i / (n - 1)
    #         scene.control_points = []
    #         for cp0, cp1 in zip(scene0.control_points, scene1.control_points):
    #             new_origin = [(a * (1 - t) + b * t) for a, b in zip(cp0["origin"], cp1["origin"])]
    #             cpx = copy.deepcopy(cp0)
    #             cpx["origin"] = new_origin
    #             scene.control_points.append(cpx)
    #         frames[i].apply_scene(scene)

    # noinspection PyPep8Naming
    def interpolate_cp_cyclic(
            self,
            keyframes: list[AScene],
            smoothness: float = 0.,
            group_specificity: float = 1.) -> tuple[CylinderSpline, np.ndarray, np.ndarray]:
        """Perform a 2D thin-plate spline fit in a cylindrical coordinate
        system to interpolate the control points smoothly both around cycles and
        between cycles.

        The number of control points in each keyframe must match exactly, and
        that number must be 3 or more.

        :param keyframes: A list of scenes which must each contain a VolumeInfo
            section used to define positions in 2D cylinder space.
        :param smoothness: The amount of regularization to use. The amplitude
            should usually be in range [0-1], but larger is valid. A smoothness
            of 0 corresponds to exactly intersecting each control point.
        :param group_specificity: The aspect ratio of the coordinate system.
            Increasing this value relaxes the curve between groups, decreasing
            the tendency to generalize across groups, aka, cycles.
        :return: The thin-plate spline object which can be used to evaluate the
            control points at additional locations, the input point array
            derived from the keyframes (X), and the output control points
            resulting from the transformation (Y). X.shape = (k, 2) and
            Y.shape = (k, 3*n) where 'k' is the number of keyframes, and 'n' is
            the number of control points contained in each.
        """

        n_kf = len(keyframes)
        assert n_kf >= 3, "Must have at least three keyframes to interpolate."
        n_cp = len(keyframes[0].control_points)
        assert all(len(k.control_points) == n_cp for k in keyframes), \
            "All keyframes must have a matching set of control points."
        cps = copy.deepcopy(keyframes[0].control_points)

        # We need to resize the group indices and the time indices onto a
        # common scale from [0-1]. Unfortunately, the max and min group indices
        # are not generally known, so we rescale based on the given batch.
        all_group_indices = (
            [kf.items["VolumeInfo"]["group_index"] for kf in keyframes]
            + [f.volume.group_index for f in self.a_frames]
        )
        min_group_index: int = min(all_group_indices)
        range_group_index: int = max(all_group_indices) - min_group_index

        X_fit = np.empty((n_kf, 2))
        Y_fit = np.empty((n_kf, 3 * n_cp))

        for i, kf in enumerate(keyframes):
            info = kf.items["VolumeInfo"]
            X_fit[i, 0] = (info["group_index"] - min_group_index) / range_group_index
            X_fit[i, 1] = info["time_index"] / info["n_times"]
            for j in range(n_cp):
                Y_fit[i, 3*j:3*(j+1)] = kf.control_points[j]["origin"]

        spline = CylinderSpline(smoothness, group_specificity)
        spline.fit(X_fit, Y_fit)

        X_out = np.empty((len(self), 2))
        for i, f in enumerate(self.a_frames):
            v: VolumeImage = f.volume
            X_out[i, 0] = (v.group_index - min_group_index) / range_group_index
            X_out[i, 1] = v.time_index / v.n_times
        Y_out = spline.transform(X_out)

        for i, f in enumerate(self.a_frames):
            for j in range(n_cp):
                cps[j]["origin"] = [float(a) for a in Y_out[i, 3*j:3*(j+1)]]
            f.scene.control_points = copy.deepcopy(cps)

        return spline, X_fit, Y_fit


def _assign_unbalanced(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Solve the unbalanced assignment problem for two arrays.

    Elements are paired to minimize the squared Euclidean distance between each
    pair. The best matches are first assigned, then the remainder are assigned
    such that no element has more than the lowest number of assignments + 1.

    :param a: An n by k list of vectors. k must match between a and b.
    :param b: An m by k list of vectors.
    :return: A max(n, m) by 2 matrix of indices into a and b representing
        the pairs assigned.
    """

    pairs_ab = np.empty((max(a.shape[0], b.shape[0]), 2), np.int64)
    dists = cdist(a, b, "sqeuclid")

    h, w = dists.shape
    if more_columns := w > h:
        N, n = w, h
    else:
        N, n = h, w

    # Keep track of which indices into "dists" remain to be chosen.
    # Only tracking the long side is necessary, since it is the one that shortens.
    long_indices = np.arange(N)

    n_iters = int(np.ceil(N / n))
    for i in range(n_iters):
        square_size = max(dists.shape)
        dists_square = np.zeros((square_size, square_size))
        dists_square[:dists.shape[0], :dists.shape[1]] = dists
        i_row, i_col = linear_sum_assignment(dists_square)

        assigned = (
            i_row < dists.shape[0]
            if dists.shape[0] < dists.shape[1]
            else i_col < dists.shape[1]
        )

        i_range = slice(i * n, (i + 1) * n)
        if more_columns:
            pairs_ab[i_range, 0] = i_row[assigned]
            pairs_ab[i_range, 1] = long_indices[i_col[assigned]]
        else:
            pairs_ab[i_range, 0] = long_indices[i_row[assigned]]
            pairs_ab[i_range, 1] = i_col[assigned]

        # Skip the end of the last iteration because more_columns inverts,
        # causing a nuisance that we don't need to deal with.
        if i == n_iters - 1:
            break
        # Delete matched pairs from the long side, shortening it.
        if more_columns:
            i_unassigned = i_col[~assigned]
            dists = dists[:, i_unassigned]
            long_indices = long_indices[i_unassigned]
        else:
            i_unassigned = i_row[~assigned]
            dists = dists[i_unassigned, :]
            long_indices = long_indices[i_unassigned]
    return pairs_ab
