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
.. module:: nxtomo_loader
   :platform: Unix
   :synopsis: A class for loading standard tomography data

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""

import h5py
import logging
import numpy as np

import savu.core.utils as cu
from savu.plugins.base_loader import BaseLoader
from savu.plugins.utils import register_plugin
from savu.data.data_structures.data_types.data_plus_darks_and_flats \
    import ImageKey, NoImageKey


@register_plugin
class NxtomoLoader(BaseLoader):
    """
    A class to load tomography data from a hdf5 file

    :param data_path: Path to the data inside the \
        file. Default: 'entry1/tomo_entry/data/data'.
    :param image_key_path: Path to the image key entry inside the nxs \
        file. Default: 'entry1/tomo_entry/instrument/detector/image_key'.
    :param dark: Optional path to the dark field data file, nxs path and \
        scale value. Default: [None, None, 1].
    :param flat: Optional Path to the flat field data file, nxs path and \
        scale value. Default: [None, None, 1].
    :param angles: A python statement to be evaluated or a file. Default: None.
    :param 3d_to_4d: Set to true if this reshape is required. Default: False.
    :param ignore_flats: List of batch numbers of flats (start at 1) to \
        ignore. Default: None.
    """

    def __init__(self, name='NxtomoLoader'):
        super(NxtomoLoader, self).__init__(name)

    def setup(self):
        exp = self.exp

        data_obj = exp.create_data_object('in_data', 'tomo')

        data_obj.backing_file = \
            h5py.File(self.exp.meta_data.get_meta_data("data_file"), 'r')

        data_obj.data = data_obj.backing_file[self.parameters['data_path']]

        self.__set_dark_and_flat(data_obj)

        if self.parameters['3d_to_4d']:
            if not self.parameters['angles']:
                raise Exception('Angles are required in the loader.')
            self.__setup_4d(data_obj)
            n_angles = self.__set_rotation_angles(data_obj)
            shape = self.__setup_3d_to_4d(data_obj, n_angles)
        else:
            if len(data_obj.data.shape) is 3:
                shape = self._setup_3d(data_obj)
            else:
                shape = self.__setup_4d(data_obj)
            self.__set_rotation_angles(data_obj)

        try:
            control = data_obj.backing_file['entry1/tomo_entry/control/data']
            data_obj.meta_data.set_meta_data("control", control[...])
        except:
            logging.warn("No Control information available")

        nAngles = len(data_obj.meta_data.get_meta_data('rotation_angle'))
        self.__check_angles(data_obj, nAngles)
        data_obj.set_original_shape(shape)
        self.set_data_reduction_params(data_obj)
        data_obj.data._set_dark_and_flat()

    def _setup_3d(self, data_obj):
        logging.debug("Setting up 3d tomography data.")
        rot = 0
        detY = 1
        detX = 2
        data_obj.set_axis_labels('rotation_angle.degrees',
                                 'detector_y.pixel',
                                 'detector_x.pixel')

        data_obj.add_pattern('PROJECTION', core_dir=(detX, detY),
                             slice_dir=(rot,))
        data_obj.add_pattern('SINOGRAM', core_dir=(detX, rot),
                             slice_dir=(detY,))
        return data_obj.data.shape

    def __setup_3d_to_4d(self, data_obj, n_angles):
        logging.debug("setting up 4d tomography data from 3d input.")
        from savu.data.data_structures.data_types.map_3dto4d_h5 \
            import Map_3dto4d_h5
        data_obj.data = Map_3dto4d_h5(data_obj.data, n_angles)
        return data_obj.data.get_shape()

    def __setup_4d(self, data_obj):
        logging.debug("setting up 4d tomography data.")
        rot = 0
        detY = 1
        detX = 2
        scan = 3

        data_obj.set_axis_labels('rotation_angle.degrees', 'detector_y.pixel',
                                 'detector_x.pixel', 'scan.number')

        data_obj.add_pattern('PROJECTION', core_dir=(detX, detY),
                             slice_dir=(rot, scan))
        data_obj.add_pattern('SINOGRAM', core_dir=(detX, rot),
                             slice_dir=(detY, scan))
        return data_obj.data.shape

    def __set_dark_and_flat(self, data_obj):
        flat = self.parameters['flat'][0]
        dark = self.parameters['dark'][0]

        if not flat and not dark:
            self.__find_dark_and_flat(data_obj)
        else:
            self.__set_separate_dark_and_flat(data_obj)

    def __find_dark_and_flat(self, data_obj):
        ignore = self.parameters['ignore_flats'] if \
            self.parameters['ignore_flats'] else None
        try:
            image_key = data_obj.backing_file[
                'entry1/tomo_entry/instrument/detector/image_key'][...]
            data_obj.data = \
                ImageKey(data_obj, image_key, 0, ignore=ignore)
            #data_obj.set_shape(data_obj.data.get_shape())
        except KeyError:
            cu.user_message("An image key was not found.")
            try:
                data_obj.data = NoImageKey(data_obj, None, 0)
                entry = 'entry1/tomo_entry/instrument/detector/'
                data_obj.data._set_flat_path(entry + 'flatfield')
                data_obj.data._set_dark_path(entry + 'darkfield')
            except KeyError:
                cu.user_message("Dark/flat data was not found in input file.")

    def __set_separate_dark_and_flat(self, data_obj):
        try:
            image_key = data_obj.backing_file[
                'entry1/tomo_entry/instrument/detector/image_key'][...]
        except:
            image_key = None
        data_obj.data = NoImageKey(data_obj, image_key, 0)
        self.__set_data(data_obj, 'flat', data_obj.data._set_flat_path)
        self.__set_data(data_obj, 'dark', data_obj.data._set_dark_path)

    def __set_data(self, data_obj, name, func):
        path, entry, scale = self.parameters[name]

        if path.split('/')[0] == 'test_data':
            import os
            path = \
                os.path.dirname(os.path.abspath(__file__))+'/../../../' + path

        ffile = h5py.File(path, 'r')
        try:
            image_key = \
                ffile['entry1/tomo_entry/instrument/detector/image_key'][...]
            func(ffile[entry], imagekey=image_key)
        except:
            func(ffile[entry])

        data_obj.data._set_scale(name, scale)

    def __set_rotation_angles(self, data_obj):
        angles = self.parameters['angles']
        if angles is None:
            try:
                entry = 'entry1/tomo_entry/data/rotation_angle'
                angles = data_obj.backing_file[entry][
                    (data_obj.data.get_image_key()) == 0, ...]
            except KeyError:
                logging.warn("No rotation angle entry found in input file.")
                angles = np.linspace(0, 180, data_obj.get_shape()[0])
        else:
            try:
                exec("angles = " + angles)
            except:
                try:
                    angles = np.loadtxt(angles)
                except:
                    raise Exception('Cannot set angles in loader.')

        data_obj.meta_data.set_meta_data("rotation_angle", angles)
        return len(angles)

    def __check_angles(self, data_obj, n_angles):
        data_angles = data_obj.data.get_shape()[0]
        if data_angles != n_angles:
            raise Exception("The number of angles %s does not match the data "
                            "dimension length %s", n_angles, data_angles)
