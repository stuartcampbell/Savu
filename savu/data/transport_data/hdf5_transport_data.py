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
.. module:: hdf5_transport_data
   :platform: Unix
   :synopsis: A data transport class that is inherited by Data class at \
   runtime. It organises the slice list and moves the data.

.. moduleauthor:: Nicola Wadeson <scientificsoftware@diamond.ac.uk>

"""
import copy
import numpy as np

from savu.data.data_structures.data_add_ons import Padding
from savu.data.transport_data.base_transport_data import BaseTransportData

NX_CLASS = 'NX_class'


class Hdf5TransportData(BaseTransportData):
    """
    The Hdf5TransportData class performs the organising and movement of data.
    """

    def __init__(self, name='Hdf5TransportData'):
        super(Hdf5TransportData, self).__init__()
        self.pad = False
        self.transfer_data = None

    def _get_process_data(self):
        return self.process_data

    def _single_slice_list(self, nSlices, nDims, core_slice, core_dirs,
                           slice_dirs, fix, index):

        fix_dirs, value = fix
        slice_list = []
        for i in range(nSlices):
            getitem = np.array([slice(None)]*nDims)
            getitem[core_dirs] = core_slice[np.arange(len(core_dirs))]
            for f in range(len(fix_dirs)):
                getitem[fix_dirs[f]] = slice(value[f], value[f] + 1, 1)
            for sdir in range(len(slice_dirs)):
                getitem[slice_dirs[sdir]] = slice(index[sdir, i],
                                                  index[sdir, i] + 1, 1)
            slice_list.append(tuple(getitem))
        return slice_list

    def _get_slice_dirs_index(self, slice_dirs, shape, value):
        """
        returns a list of arrays for each slice dimension, where each array
        gives the indices for that slice dimension.
        """
        # create the indexing array
        chunk, length, repeat = self.__chunk_length_repeat(slice_dirs, shape)
        values = None
        idx_list = []
        for i in range(len(slice_dirs)):
            c = chunk[i]
            r = repeat[i]
            exec('values = ' + value)
            idx = np.ravel(np.kron(values, np.ones((r, c))))
            idx_list.append(idx.astype(int))
        return np.array(idx_list)

    def __chunk_length_repeat(self, slice_dirs, shape):
        """
        For each slice dimension, determine 3 values relevant to the slicing.

        :returns: chunk, length, repeat
            chunk: how many repeats of the same index value before an increment
            length: the slice dimension length (sequence length)
            repeat: how many times does the sequence of chunked numbers repeat
        :rtype: [int, int, int]
        """
        sshape = self.__get_shape_of_slice_dirs(slice_dirs, shape)
        if not slice_dirs:
            return [1], [1], [1]

        chunk = []
        length = []
        repeat = []
        for dim in range(len(slice_dirs)):
            chunk.append(int(np.prod(sshape[0:dim])))
            length.append(sshape[dim])
            repeat.append(int(np.prod(sshape[dim+1:])))
        return chunk, length, repeat

    def __get_shape_of_slice_dirs(self, slice_dirs, shape):
        sshape = [shape[sslice] for sslice in slice_dirs]
        if 'var' in sshape:
            shape = list(shape)
            for index, value in enumerate(shape):
                if isinstance(value, str):
                    shape[index] = \
                        len(self.data_info.get('axis_labels')[index])
            shape = tuple(shape)
            sshape = [shape[sslice] for sslice in slice_dirs]
        return sshape

    def _get_slice_dir_index(self, dim, boolean=False):
        starts, stops, steps, chunks = \
            self.get_preview().get_starts_stops_steps()
        if chunks[dim] > 1:
            dir_idx = np.ravel(np.transpose(self._get_slice_dir_matrix(dim)))
            if boolean:
                return self.__get_bool_slice_dir_index(dim, dir_idx)
            return dir_idx
        else:
            fix_dirs, value = self._get_plugin_data()._get_fixed_dimensions()
            if dim in fix_dirs:
                return value[fix_dirs.index(dim)]
            else:
                return np.arange(starts[dim], stops[dim], steps[dim])

    def __get_bool_slice_dir_index(self, dim, dir_idx):
        shape = self.data_info.get('orig_shape')[dim]
        bool_idx = np.ones(shape, dtype=bool)
        bool_idx[dir_idx] = True
        return bool_idx

    def _get_slice_dir_matrix(self, dim):
        starts, stops, steps, chunks = \
            self.get_preview().get_starts_stops_steps()
        chunk = chunks[dim]
        a = np.tile(np.arange(starts[dim], stops[dim], steps[dim]), (chunk, 1))
        b = np.transpose(np.tile(np.arange(chunk)-chunk/2, (a.shape[1], 1)))
        dim_idx = a + b
        if dim_idx[dim_idx < 0].size:
            raise Exception('Cannot have a negative value in the slice list.')
        return dim_idx

    def _get_core_slices(self, core_dirs):
        core_slice = []
        starts, stops, steps, chunks = \
            self.get_preview().get_starts_stops_steps()

        for c in core_dirs:
            if (chunks[c]) > 1:
                if (stops[c] - starts[c] == 1):
                    start = starts[c] - int(chunks[c]/2)
                    if start < 0:
                        raise Exception('Cannot have a negative value in the '
                                        'slice list.')
                    stop = starts[c] + (chunks[c] - int(chunks[c]/2))
                    core_slice.append(slice(start, stop, 1))
                else:
                    raise Exception("The core dimension does not support "
                                    "multiple chunks.")
            else:
                core_slice.append(slice(starts[c], stops[c], steps[c]))
        return np.array(core_slice)

    def _banked_list(self, slice_list):
        shape = self.get_shape()
        slice_dirs = self.get_slice_dimensions()
        chunk, length, repeat = self.__chunk_length_repeat(slice_dirs, shape)
        banked = self._split_list(slice_list, length[0])
        return banked, length, slice_dirs

    def _group_dimension(self, sl, dim, step):
        start = sl[0][dim].start
        stop = sl[-1][dim].stop
        working_slice = list(sl[0])
        working_slice[dim] = slice(start, stop, step)
        return tuple(working_slice)

    def _split_list(self, the_list, size):
            return [the_list[x:x+size] for x in xrange(0, len(the_list), size)]

    # This method only works if the split dimensions in the slice list contain
    # slice objects
    def __split_frames(self, slice_list, split_list):
        split = [map(int, a.split('.')) for a in split_list]
        dims = [s[0] for s in split]
        length = [s[1] for s in split]
        replace = self.__get_split_frame_entries(slice_list, dims, length)
        # now replace each slice list entry with multiple entries
        array_list = []
        for sl in slice_list:
            new_list = np.array([sl for i in range(len(replace[0]))])
            for d, i in zip(dims, range(len(dims))):
                new_list[:, d] = replace[i]
            array_list += [tuple(a) for a in new_list]

        return tuple(array_list)

    def __get_split_frame_entries(self, slice_list, dims, length):
        shape = self.get_shape
        replace = []
        seq_len = []

        # get the new entries
        for d, l in zip(dims, length):
            sl = slice_list[0][d]
            start = 0 if sl.start is None else sl.start
            stop = shape[d] if sl.stop is None else sl.stop
            inc = l*sl.step if sl.step else l
            temp_list = [slice(a, a+inc) for a in np.arange(start, stop, inc)]
            if temp_list[-1].stop > stop:
                temp = temp_list[-1]
                temp_list[-1] = slice(temp.start, stop, temp.step)
            replace.append(temp_list)
            seq_len.append(len(temp_list))

        # calculate the permutations
        length = np.array(seq_len)
        chunk = [int(np.prod(length[0:dim])) for dim in range(len(dims))]
        repeat = [int(np.prod(length[dim+1:])) for dim in range(len(dims))]
        full_replace = []
        for d in range(len(dims)):
            temp = [[replace[d][i]]*chunk[d] for x in range(repeat[d]) for i
                    in range(len(replace[d]))]
            full_replace.append([t for sub in temp for t in sub])
        return full_replace

    def __combine_dicts(self, d1, d2):
        for key, value in d2.iteritems():
            d1[key] = value
        return d1

    def _get_slice_lists_per_process(self, dtype):
        self.__set_padding_dict()
        self.pad = True if self._get_plugin_data().padding else False
        self.transfer_data = TransferData(dtype, self)
        trans_dict = self.transfer_data._get_dict()
        proc_dict = ProcessData(dtype, self)._get_dict()
        return self.__combine_dicts(trans_dict, proc_dict)

    def _get_frames_per_process(self, slice_list):
        processes = self.exp.meta_data.get("processes")
        process = self.exp.meta_data.get("process")
        frame_idx = np.arange(len(slice_list))
        try:
            frames = np.array_split(frame_idx, len(processes))[process]
            slice_list = slice_list[frames[0]:frames[-1]+1]
        except IndexError:
            slice_list = []
        return slice_list, frames

    def _pad_slice_list(self, slice_list, inc_start_str, inc_stop_str):
        """ Amend the slice lists to include padding.  Includes variations for
        transfer and process slice lists. """
        if not self._get_plugin_data().padding:
            return slice_list

        pad_dict = self._get_plugin_data().padding._get_padding_directions()

        shape = self.get_shape()
        for ddir, value in pad_dict.iteritems():
            exec('inc_start = ' + inc_start_str)
            exec('inc_stop = ' + inc_stop_str)
            for i in range(len(slice_list)):
                slice_list[i] = list(slice_list[i])
                sl = slice_list[i][ddir]
                if sl.start is None:
                    sl = slice(0, shape[ddir], 1)
                slice_list[i][ddir] = \
                    slice(sl.start + inc_start, sl.stop + inc_stop, sl.step)
                slice_list[i] = tuple(slice_list[i])
        return slice_list

    def _fix_list_length(self, sl, length):
        sdir = self.get_slice_dimensions()[0]
        sl = list(sl)
        e = sl[sdir]
        if (e.stop - e.start) < length:
            diff = length - (e.stop - e.start)
            sl[sdir] = slice(e.start, e.stop + diff, e.step)
        return tuple(sl)

    def __set_padding_dict(self):
        pData = self._get_plugin_data()
        if pData.padding and not isinstance(pData.padding, Padding):
            pData.pad_dict = copy.deepcopy(pData.padding)
            pData.padding = Padding(pData)
            for key in pData.pad_dict.keys():
                getattr(pData.padding, key)(pData.pad_dict[key])

    def _get_padded_data(self, slice_list, end=False):
        return self.transfer_data._get_padded_data(slice_list, end=False)


class TransferData(object):
    """
    The TransferData class organises the movement and slicing of the data from
    file.
    """

    def __init__(self, dtype, data):
        self.dtype = dtype  # in or out TransferData object
        self.data = data
        self.pData = self.data._get_plugin_data()
        self.shape = self.data.get_shape()

    def _get_dict(self):
        return self._get_dict_in() if self.dtype == 'in' else \
            self._get_dict_out()

    def _get_dict_in(self):
        sl_dict = {}
        mfp = self.pData._get_max_frames_process()
        mft = self.pData._get_max_frames_transfer()
        sl, sl_dict['current'] = \
            self._get_slice_list(self.shape, current_sl=True)

        if self.pData._get_boundary_padding():
            for i in range(len(sl)):
                sl[i] = self.data._fix_list_length(sl[i], mfp)
        else:
            sl[-1] = self.data._fix_list_length(sl[-1], mft)

        sl, sl_dict['frames'] = self.data._get_frames_per_process(sl)
        if self.data.pad:
            sl = self.data._pad_slice_list(
                sl, "-value['before']", "value['after']")
        sl_dict['transfer'] = sl
        return sl_dict

    def _get_dict_out(self):
        sl_dict = {}
        sl = self._get_slice_list(self.shape)
        sl_dict['transfer'], _ = self.data._get_frames_per_process(sl)
        return sl_dict

    def _get_slice_list(self, shape, current_sl=False):
        mft = self.pData._get_max_frames_transfer()
        mfp = self.pData._get_max_frames_process()
        transfer_ssl = self._local_single_slice_list(shape)

        if transfer_ssl is None:
            raise Exception("Data type %s does not support slicing in "
                            "directions %s" % (self.get_current_pattern_name(),
                                               self.get_slice_directions()))
        slice_dir = self.data.get_slice_dimensions()
        transfer_gsl = \
            self.__grouped_slice_list(transfer_ssl, mft, slice_dir)

        split_list = self.pData.split
        transfer_gsl = self.__split_frames(transfer_gsl, split_list) if \
            split_list else transfer_gsl

        if current_sl:
            temp = ProcessData('in', self.data)
            current_sl = \
                temp._grouped_slice_list(transfer_ssl, mfp, slice_dir[0])
            return transfer_gsl, current_sl
        return transfer_gsl

    def _local_single_slice_list(self, shape):
        pData = self.pData
        slice_dirs = self.data.get_slice_dimensions()
        core_dirs = np.array(self.data.get_core_dimensions())
        fix = pData._get_fixed_dimensions()
        core_slice = self.data._get_core_slices(core_dirs)
        values = 'self._get_slice_dir_index(slice_dirs[i])'
        index = self.data._get_slice_dirs_index(slice_dirs, shape, values)
        nSlices = index.shape[1] if index.size else len(fix[0])
        nDims = len(shape)
        ssl = self.data._single_slice_list(
            nSlices, nDims, core_slice, core_dirs, slice_dirs, fix, index)
        return ssl

    def __grouped_slice_list(self, slice_list, max_frames, group_dim):
        if group_dim is None:
            return slice_list
        steps = self.data.get_preview().get_starts_stops_steps('steps')
        sub_groups = self.data._split_list(slice_list, max_frames)
        grouped = []

        for sub in sub_groups:
            temp = list(sub[0])
            for dim in group_dim:
                temp[dim] = \
                    self.data._group_dimension(sub, dim, steps[dim])[dim]
            grouped.append(tuple(temp))
        return grouped

    def _get_padded_data(self, slice_list, end=False):
#        if not self.pad and not end:
#            return self.data[tuple(slice_list)]
        slice_list = list(slice_list)
        pData = self.pData
        pad_dims = list(set(self.data.get_core_dimensions() +
                            (self.data.get_slice_dimensions()[0],)))
        pad_list = []
        for i in range(len(slice_list)):
            pad_list.append([0, 0])

        temp = self.data.data.shape
        shape = temp if len(temp) == len(slice_list) else self.data.get_shape()

        for dim in range(len(pad_dims)):
            sl = slice_list[dim]
            if sl.start < 0:
                pad_list[dim][0] = -sl.start
                slice_list[dim] = slice(0, sl.stop, sl.step)
            diff = sl.stop - shape[dim]
            if diff > 0:
                pad_list[dim][1] = diff
                slice_list[dim] = \
                    slice(slice_list[dim].start, sl.stop - diff, sl.step)

        data = self.data.data[tuple(slice_list)]

        if np.sum(pad_list):
            mode = pData.padding.mode if pData.padding else 'edge'
            temp = np.pad(data, tuple(pad_list), mode=mode)
            return temp
        return data


class ProcessData(object):
    """
    The ProcessData class organises the slicing of transferred data to give the
    shape requested by a plugin for each run of 'process_frames'.
    """

    def __init__(self, dtype, data):
        self.dtype = dtype  # in or out ProcessData object
        self.data = data
        self.pData = data._get_plugin_data()
        self.shape = data.get_shape()
        self.sdir = None
        self.remove_dims = []

    def _get_dict(self):
        return self._get_dict_in() if self.dtype == 'in' else \
            self._get_dict_out()

    def _get_dict_in(self):
        sl_dict = {}
        mfp = self.pData._get_max_frames_process()
        sl = self._get_slice_list()

        # does this do anything?
        if self.sdir:
            sl[-1] = self.data._fix_list_length(sl[-1], mfp)

        sl = self.data._pad_slice_list(sl, '0', 'sum(value.values())')
        sl_dict['process'] = sl
        return sl_dict

    def _get_dict_out(self):
        sl_dict = {}
        sl_dict['process'] = self._get_slice_list()
        sl_dict['unpad'] = self.__get_unpad_slice_list(len(sl_dict['process']))
        return sl_dict

    def _get_slice_list(self):
        """ Splits a file transfer slice list into a list of (padded) slices
        required for each loop of process_frames.
        """
        pData = self.pData
        mf_process = pData.meta_data.get('max_frames_process')
        shape = pData.get_shape_transfer()
        process_ssl = self._local_single_slice_list(shape)
        process_gsl = \
            self._grouped_slice_list(process_ssl, mf_process, self.sdir)
        return process_gsl

    def _local_single_slice_list(self, shape):
        slice_dirs = self.data.get_slice_dimensions()
        core_dirs = np.array(self.data.get_core_dimensions())
        fix = [[]]*2
        core_slice = np.array([slice(None)]*len(core_dirs))
        shape = tuple([shape[i] for i in range(len(shape)) if i not in
                       self.remove_dims])
        values = 'np.arange(shape[slice_dirs[i]])'
        index = self.data._get_slice_dirs_index(slice_dirs, shape, values)
        # there may be no slice dirs if process is True
        index = index if index.size else np.array([[0]])
        nSlices = index.shape[1] if index.size else len(fix[0])
        nDims = len(shape)

        ssl = self.data._single_slice_list(
            nSlices, nDims, core_slice, core_dirs, slice_dirs, fix, index)
        self.sdir = slice_dirs[0] if len(slice_dirs) > 0 else None
        return ssl

    def _grouped_slice_list(self, slice_list, max_frames, group_dim):
        if group_dim is None:
            return slice_list

        banked, length, slice_dir = self.data._banked_list(slice_list)
        grouped = []
        for group in banked:
            sub_groups = self.data._split_list(group, max_frames)
            for sub in sub_groups:
                grouped.append(self.data._group_dimension(sub, group_dim, 1))
        return grouped

    def __get_unpad_slice_list(self, reps):
        sl = [slice(None)]*len(self.pData.get_shape_transfer())
        if not self.pData.padding:
            return tuple([tuple(sl)]*reps)
        pad_dict = self.pData.padding._get_padding_directions()
        for ddir, value in pad_dict.iteritems():
            sl[ddir] = slice(value['before'], -value['after'])
        return tuple([tuple(sl)]*reps)
