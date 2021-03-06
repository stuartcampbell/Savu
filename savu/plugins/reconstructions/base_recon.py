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
.. module:: base_recon
   :platform: Unix
   :synopsis: A base class for all reconstruction methods

.. moduleauthor:: Mark Basham <scientificsoftware@diamond.ac.uk>

"""
import math

from savu.plugins.plugin import Plugin
import numpy as np


class BaseRecon(Plugin):
    """
    A base class for reconstruction plugins

    :u*param centre_of_rotation: Centre of rotation to use for the \
        reconstruction. Default: 0.0.
    :u*param init_vol: Dataset to use as volume initialiser \
        (doesn't currently work with preview). Default: None.
    :param sino_pad: Pad the sinogram to remove edge artefacts in the \
        reconstructed ROI (NB. This will increase the size of the data and \
        the time taken to perform the reconstruction). Default: False.
    :u*param log: Take the log of the data before reconstruction \
        (True or False). Default: True.
    :u*param preview: A slice list of required frames. Default: [].
    """
    count = 0

    def __init__(self, name='BaseRecon'):
        super(BaseRecon, self).__init__(name)
        self.nOut = 1
        self.nIn = 1
        self.scan_dim = None
        self.rep_dim = None
        self.br_vol_shape = None
        self.frame_angles = None
        self.frame_cors = None
        self.frame_init_data = None
        self.centre = None

    def base_dynamic_data_info(self):
        if self.parameters['init_vol']:
            if len(self.parameters['init_vol'].split('.')) is 3:
                name, temp, self.rep_dim = self.parameters['init_vol']
                self.parameters['init_vol'] = name
            self.nIn += 1
            self.parameters['in_datasets'].append(self.parameters['init_vol'])

    def base_pre_process(self):
        in_data, out_data = self.get_datasets()
        in_pData, out_pData = self.get_plugin_datasets()
        self.pad_dim = \
            in_pData[0].get_data_dimension_by_axis_label('x', contains=True)
        in_meta_data = self.get_in_meta_data()[0]

        self.set_centre_of_rotation(in_data[0], in_meta_data, in_pData[0])
        self.exp.log(self.name + " End")
        self.br_vol_shape = out_pData[0].get_shape()

        self.main_dir = in_pData[0].get_pattern()['SINOGRAM']['main_dir']
        self.angles = in_meta_data.get('rotation_angle')
        if len(self.angles.shape) is not 1:
            self.scan_dim = in_data[0].get_data_dimension_by_axis_label('scan')
        self.slice_dirs = out_data[0].get_slice_dimensions()

        shape = in_pData[0].get_shape()
        pad_len = shape[self.pad_dim] if self.parameters['sino_pad'] else 0

        # this is the correct value but doesn't give a good result
        self.sino_pad = int(math.ceil((math.sqrt(2)-1)*pad_len))
        #self.sino_pad = int(0.5*pad_len)
#        bases = [b.__name__ for b in self.__class__.__bases__]
        # pad the data now if the recon is not astra
#        self.sino_func, self.cor_func = self.set_function(False) if \
#            'NewBaseAstraRecon' in bases else self.set_function(shape)
        self.sino_func, self.cor_func = self.set_function(False)

    def get_vol_shape(self):
        return self.br_vol_shape

    def set_centre_of_rotation(self, inData, mData, pData):
        if 'centre_of_rotation' in mData.get_dictionary().keys():
            cor = mData.get('centre_of_rotation')
        else:
            cor = np.ones(inData.get_shape()[pData.get_slice_dimension()])
            cor *= self.parameters['centre_of_rotation']
        self.cor = cor
        self.centre = self.cor[0]

    def set_function(self, pad_shape):
        if not pad_shape:
            cor_func = lambda cor: cor
            if self.parameters['log']:
                sino_func = lambda sino: -np.log(np.nan_to_num(sino)+1)
            else:
                sino_func = lambda sino: np.nan_to_num(sino)
        else:
            cor_func = lambda cor: cor+self.sino_pad
            pad_tuples = [(0, 0)]*(len(pad_shape)-1)
            pad_tuples.insert(self.pad_dim, (self.sino_pad, self.sino_pad))
            pad_tuples = tuple(pad_tuples)
            if self.parameters['log']:
                sino_func = lambda sino: -np.log(np.nan_to_num(
                    np.pad(sino, pad_tuples, 'edge'))+1)
            else:
                sino_func = lambda sino: np.nan_to_num(np.pad(
                    sino, pad_tuples, 'edge'))
        return sino_func, cor_func

    def base_process_frames(self, data):
        """
        Reconstruct a single sinogram with the provided centre of rotation
        """
        sl = self.get_current_slice_list()[0]
        init = data[1] if len(data) is 2 else None
        angles = \
            self.angles[:, sl[self.scan_dim]] if self.scan_dim else self.angles
        self.frame_angles = angles

        dim_sl = sl[self.main_dir]
        self.frame_cors = self.cor_func(self.cor[dim_sl])
        if not self.frame_cors.shape:
            self.frame_cors = np.array([self.centre])
        len_data = len(np.arange(dim_sl.start, dim_sl.stop, dim_sl.step))

        missing = [self.centre]*(len(self.frame_cors) - len_data)
        self.frame_cors = np.append(self.frame_cors, missing)

        self.frame_init_data = init
        data[0] = self.sino_func(data[0])
        return data

    def get_angles(self):
        """ Get the angles associated with the current sinogram(s).

        :returns: Angles of the current frames.
        :rtype: np.ndarray
        """
        return self.frame_angles

    def get_cors(self):
        """
        Get the centre of rotations associated with the current sinogram(s).

        :returns: Centre of rotation values for the current frames.
        :rtype: np.ndarray
        """
        return self.frame_cors

    def get_initial_data(self):
        """
        Get the initial data (if it is exists) associated with the current \
        sinogram(s).

        :returns: The section of the initialisation data associated with the \
            current frames.
        :rtype: np.ndarray or None
        """
        return self.frame_init_data

    def get_frame_params(self):
        params = [self.get_cors(), self.get_angles(), self.get_vol_shape(),
                  self.get_initial_data()]
        return params

    def setup(self):
        in_dataset, out_dataset = self.get_datasets()

        # reduce the data as per data_subset parameter
        in_dataset[0].get_preview().set_preview(self.parameters['preview'])

        # set information relating to the plugin data
        in_pData, out_pData = self.get_plugin_datasets()

        in_pData[0].plugin_data_setup('SINOGRAM', self.get_max_frames())
        if len(in_pData) is 2:
            from savu.data.data_structures.data_types import Replicate
            if self.rep_dim:
                in_dataset[1].data = Replicate(
                    in_dataset[1], in_dataset[0].get_shape(self.rep_dim))
            in_pData[1].plugin_data_setup('VOLUME_XZ', self.get_max_frames())

        axis_labels = in_dataset[0].data_info.get('axis_labels')[0]

        dim_volX, dim_volY, dim_volZ = \
            self.map_volume_dimensions(in_dataset[0], in_pData[0])

        axis_labels = [0]*3
        axis_labels = {in_dataset[0]:
                       [str(dim_volX) + '.voxel_x.voxels',
                        str(dim_volY) + '.voxel_y.voxels',
                        str(dim_volZ) + '.voxel_z.voxels']}

        shape = list(in_dataset[0].get_shape())
        shape[dim_volX] = shape[dim_volZ]

        out_dataset[0].create_dataset(axis_labels=axis_labels,
                                      shape=tuple(shape))

        out_dataset[0].add_volume_patterns(dim_volX, dim_volY, dim_volZ)

        # set pattern_name and nframes to process for all datasets
        out_pData[0].plugin_data_setup('VOLUME_XZ', self.get_max_frames())

    def get_max_frames(self):
        return 'multiple'

    def map_volume_dimensions(self, data, pData):
        data._finalise_patterns()
        dim_rotAngle = data.get_data_patterns()['PROJECTION']['main_dir']
        dim_detY = data.get_data_patterns()['SINOGRAM']['main_dir']

        core_dirs = data.get_core_dimensions()
        dim_detX = list(set(core_dirs).difference(set((dim_rotAngle,))))[0]

        dim_volX = dim_rotAngle
        dim_volY = dim_detY
        dim_volZ = dim_detX
        return dim_volX, dim_volY, dim_volZ

    def nInput_datasets(self):
        return self.nIn

    def nOutput_datasets(self):
        return self.nOut

    def reconstruct_pre_process(self):
        """
        Should be overridden to perform pre-processing in a child class
        """
        pass
