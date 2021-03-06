# Copyright 2014 Diamond Light Source Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
.. module:: dark_flat_field_correction
   :platform: Unix
   :synopsis: A Plugin to apply a simple dark and flatfield correction to raw\
       timeseries data

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""

import numpy as np

from savu.plugins.driver.cpu_plugin import CpuPlugin
from savu.plugins.corrections.base_correction import BaseCorrection
from savu.plugins.utils import register_plugin


@register_plugin
class DarkFlatFieldCorrection(BaseCorrection, CpuPlugin):
    """
    A Plugin to apply a simple dark and flat field correction to data.
    :param pattern: Data processing pattern is 'PROJECTION' or \
        'SINOGRAM'. Default: 'PROJECTION'.
    :param lower_bound: Set all values below the lower_bound to this \
        value. Default: None.
    :param upper_bound: Set all values above the upper bound to this \
        value. Default: None.
    :param warn_proportion: Output a warning if this proportion of values, \
        or greater, are below and/or above the lower/upper bounds, \
        e.g enter 0.05 for 5%. Default: 0.05.
    """

    def __init__(self):
        super(DarkFlatFieldCorrection,
              self).__init__("DarkFlatFieldCorrection")
        self.flag_low_warning = False
        self.flag_high_warning = False
        self.flag = True

    def pre_process(self):
        inData = self.get_in_datasets()[0]
        in_pData = self.get_plugin_in_datasets()[0]
        self.dark = inData.meta_data.get('dark')
        self.flat = inData.meta_data.get('flat')

        pData_shape = in_pData.get_shape()
        tile = [1]*len(pData_shape)
        rot_dim = inData.get_data_dimension_by_axis_label('rotation_angle')
        self.slice_dir = in_pData.get_slice_dimension()

        if self.parameters['pattern'] == 'PROJECTION':
            self._proj_pre_process(inData, pData_shape, tile, rot_dim)
        elif self.parameters['pattern'] == 'SINOGRAM':
            self._sino_pre_process(inData, tile, rot_dim)

        self.flat_minus_dark = self.flat - self.dark
        self.warn = self.parameters['warn_proportion']
        self.low = self.parameters['lower_bound']
        self.high = self.parameters['upper_bound']

    def _proj_pre_process(self, data, shape, tile, dim):
        tile[dim] = shape[dim]
        self.convert_size = lambda x: np.tile(x, tile)
        self.process_frames = self.correct_proj

    def _sino_pre_process(self, data, tile, dim):
        full_shape = data.get_shape()
        tile[dim] = full_shape[dim]
        self.process_frames = self.correct_sino
        self.length = full_shape[self.slice_dir]
        if len(full_shape) is 3:
            self.convert_size = lambda a, b, x: np.tile(x[a:b], tile)
        else:
            nSino = \
                full_shape[data.get_data_dimension_by_axis_label('detector_y')]
            self.convert_size = \
                lambda a, b, x: np.tile(x[a % nSino:b], tile)
        self.count = 0

    def correct_proj(self, data):
        data = data[0]
        dark = self.convert_size(self.dark)
        flat_minus_dark = self.convert_size(self.flat_minus_dark)
        data = np.nan_to_num((data-dark)/flat_minus_dark)
        self.__data_check(data)
        return data

    def correct_sino(self, data):
        data = data[0]
        sl = self.get_current_slice_list()[0][self.slice_dir]
        nFrames = min(self.get_max_frames(), self.length)
        reps_at = int(np.ceil(self.length/float(nFrames)))
        current_idx = self.get_global_frame_index()[0][self.count]
        start = (current_idx % reps_at)*nFrames
        end = start + len(np.arange(sl.start, sl.stop, sl.step))

        dark = self.convert_size(start, end, self.dark)
        flat_minus_dark = \
            self.convert_size(start, end, self.flat_minus_dark)
        data = np.nan_to_num((data-dark)/flat_minus_dark)
        self.__data_check(data)
        self.count += 1
        return data

    def fixed_flag(self):
        if self.parameters['pattern'] == 'PROJECTION':
            return True
        else:
            return False

    def __data_check(self, data):
        # make high and low crop masks and flag if those masks include a large
        # proportion of pixels, as this may indicate a failure
        if not self.low and not self.high:
            return

        if self.low:
            low_crop = data < self.parameters['lower_bound']
            if ((float(low_crop.sum()) / low_crop.size) > self.warn):
                self.flag_low_warning = True
            # Set all cropped values to the crop level
            data[low_crop] = self.parameters['lower_bound']
        if self.high:
            high_crop = data > self.parameters['upper_bound']
            if ((float(high_crop.sum()) / high_crop.size) > self.warn):
                self.flag_high_warning = True
            # Set all cropped values to the crop level
            data[low_crop] = self.parameters['lower_bound']

    def executive_summary(self):
        summary = []
        if self.flag_high_warning:
            summary.append(("WARNING: over %i%% of pixels are being clipped " +
                            "as they have %f times the intensity of the " +
                            "provided flat field. Check your Dark and Flat " +
                            "correction images") % (self.warn*100, self.high))

        if self.flag_low_warning:
            summary.append(("WARNING: over %i%% of pixels are being clipped " +
                            "as they below the expected lower corrected " +
                            "threshold of  %f. Check your Dark and Flat " +
                            "correction images") % (self.warn*100, self.low))
        if len(summary) > 0:
            return summary

        return ["Nothing to Report"]
