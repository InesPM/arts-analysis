""" Tools for io as well as creating training 
	and test data sets. 
"""

import os

import time
import numpy as np
import h5py
import glob
import pickle

try:
    import matplotlib.pylab as plt
except:
    pass 

try:
    import filterbank as filterbank_
except:
    pass



def write_to_fil(data, header, fn):
        try:
            del header['rawdatafile']
        except KeyError:
            pass
	filterbank_.create_filterbank_file(
		fn, header, spectra=data, mode='readwrite')
	print("Writing to %s" % fn)

def write_snippet(data, fnout, header_fil=None):
        """ Take numpy array data (nfreq, ntime)
        and write to filterbank file fn
        """
        if header_fil is None:
                header_fil = fn
        header = read_fil_data(header_fil, start=0, stop=1)[-1]
        write_to_fil(data.transpose(), header, fnout)

def read_fil_data(fn, start=0, stop=1):
        """ Read in filterbank data object starting 
        at sample start and reading in chunksize stop.
        """
	print("Reading filterbank file %s \n" % fn)
	fil_obj = filterbank_.FilterbankFile(fn)
	header = fil_obj.header
        header_size = fil_obj.header_size
        header['hdr'] = header_size
	delta_t = fil_obj.header['tsamp'] # delta_t in seconds
	fch1 = header['fch1']
	nchans = header['nchans']
	foff = header['foff']
	fch_f = fch1 + nchans*foff
	freq = np.linspace(fch1, fch_f, nchans)

	try:
		data = fil_obj.get_spectra(start, stop)
	except(ValueError):
		data = 0
	# turn array into time-major, for preprocess
#	data = data.transpose() 

	return data, freq, delta_t, header

def read_whole_filterbank(fn, chunksize=1e6, t_res=1):
	""" t_res = time resolution in seconds
	"""
	data_full = []

	ii=0
	while True:
		data, freq, delta_t, header = read_fil_data(fn, start=chunksize*ii, stop=chunksize)
		print(ii, data.data.shape)

		if len(data.data[0])==0:
			break

		nt_rebin = np.int(t_res/delta_t)
		nt_rebin = min(nt_rebin, data.numspectra)
		data.downsample(nt_rebin)

		data_full.append(data.data)
		delta_t_full = data.dt

		ii+=1 

	data_full = np.concatenate(data_full, axis=-1)

	return data_full

def rebin_arr(data, n0_f=1, n1_f=1):
	""" Rebin 2d array data to have shape 
		(n0_f, n1_f)
	"""
	assert len(data.shape)==2

	n0, n1 = data.shape
	data_rb = data[:n0//n0_f * n0_f, :n1//n1_f * n1_f]
	data_rb = data_rb.reshape(n0_f, n0//n0_f, n1_f, n1//n1_f)
	data_rb = data_rb.mean(1).mean(-1)
	
	return data_rb

def im(data, title='',figname='out.png'):
	fig = plt.figure()#
	plt.imshow(data, aspect='auto', interpolation='nearest', cmap='Greys')
	plt.savefig(figname)
	plt.title(title)
	plt.show()

def combine_data_DT(fn):
	""" Combine the training set data in DM / Time space, 
	assuming text file with lines:

	# filepath label
	DM20-100_vdif_assembler+a=00+n=02_DM-T_ +11424.89s.npy 0
	DM20-100_vdif_assembler+a=00+n=02_DM-T_ +19422.29s.npy 1
	DM20-100_vdif_assembler+a=00+n=02_DM-T_ +21658.40s.npy 0

	e.g. usage: combine_data_DT('./single_pulse_ml/data/test/data_list_DM.txt')
	"""

	f = open(fn,'r')

	data_full, y = [], []
	k=0
	for ff in f:
		fn = './single_pulse_ml/data/' + ff.strip()[:-2]
		try:
			data = np.load(fn)
		except ValueError:
			continue
		k+=1
		label = int(ff[-2])
		y.append(label)
		data = normalize_data(data)
		data = rebin_arr(data, 64, 250)

		data_full.append(data)

	ndm, ntimes = data.shape

	data_full = np.concatenate(data_full, axis=0)
	data_full.shape = (k, -1)

	return data_full, np.array(y)

def combine_data_FT(fn):
	""" combine_data_FT('./single_pulse_ml/data/data_list')
	"""
	f = open(fn,'r')

	# data and its label class
	data_full, y = [], []

	for ff in f:
		line = ff.split(' ')

		fn, label = line[0], int(line[1])

		y.append(label)
		print(fn)
		tstamp = fn.split('+')[-2]
				
		#fdm = glob.glob('./*DM-T*%s*.npy' % tstamp)
		fn = './single_pulse_ml/data/test/' + fn
		data = read_pathfinder_npy(fn)
		data = normalize_data(data)
		data_full.append(data)
	
	nfreq, ntimes = data.shape[0], data.shape[-1]

	data_full = np.concatenate(data_full, axis=0)
	data_full.shape = (-1, nfreq*ntimes)

	return data_full, np.array(y)

def write_data(data, y, fname='out'):
	training_arr = np.concatenate((data, y[:, None]), axis=-1)

	np.save(fname, training_arr)


def read_data(fn):
	arr = np.load(fn)
	data, y = arr[:, :-1], arr[:, -1]

	return data, y

def read_pkl(fn):
	if fn[-4:]!='.pkl': fn+='.pkl'

	file = open(fn, 'rb')

	model = pickle.load(file)

	return model

def write_pkl(model, fn):
	if fn[-4:]!='.pkl': fn+='.pkl'
	
	file = open(fn, 'wb')
	pickle.dump(model, file)

	print("Wrote to pkl file: %s" % fn)

def get_labels():
	""" Cross reference DM-T files with Freq-T 
		files and create a training set in DM-T space. 
	"""

	fin = open('./single_pulse_ml/data/data_list','r')
	fout = open('./single_pulse_ml/data/data_list_DM','a')

	for ff in fin:
		x = ff.split(' ')
		n, c = x[0], int(x[1])
		try:
			t0 = n.split('+')[-2]
			float(t0)
		except ValueError:
			t0 = n.split('+')[-1].split('s')[0]

		newlist = glob.glob('./single_pulse_ml/data/DM*DM*%s*' % t0)

		if len(newlist) > 0:
			string = "%s %s\n" % (newlist[0].split('/')[-1], c)
			fout.write(string)

def create_training_set(FT=True, fout='./single_pulse_ml/data/data_freqtime_train'):
	if FT:
		data, y = combine_data_FT()
	else:
		data, y = combine_data_DT()

	write_data(data, y, fname=fout)

def shuffle_array(data_1, data_2=None):
	""" Take one or two data array(s), shuffle 
	in place, and shuffle the second array in the same 
	ordering, if applicable.
	"""
	ntrigger = len(data_1)
	index = np.arange(ntrigger)
	
	if data_1.shape > 2:
		data_1 = data_1.reshape(ntrigger, -1)
		data_2 = data_2.reshape(ntrigger, -1)

	data_1_ = np.concatenate((data_1, index[:, None]), axis=-1)
	np.random.shuffle(data_1_)
	index_shuffle = (data_1_[:, -1]).astype(int)
	data_2 = data_2[index_shuffle]

	return data_1_[:, :-1], data_2

filhdr_Apertif = {'telescope_id': 2,
      'az_start': 0.0,
      'nbits': 8,
      'source_name': 'J1813-1749',
      'data_type': 1,
      'nchans': 1536,
      'machine_id': 15,
      'tsamp': 8.192e-5,
      'foff': -0.1953125,
      'src_raj': 181335.2,
      'src_dej': -174958.1,
      'tstart': 58523.3437492,
      'nbeams': 1,
      'fch1': 1519.50561523,
      'za_start': 0.0,
      'rawdatafile': '',
      'nifs': 1,
      #'nsamples': 12500
      }


def create_new_filterbank(fnfil, telescope='Apertif'):
   if telescope in ('ASKAP', 'Askap', 'askap'):
      filhdr = filhdr_ASKAP
   elif telescope in ('Apertif', 'APERTIF', 'apertif'):
      filhdr = filhdr_Apertif
   elif telescope in ('CHIME', 'Chime', 'chime'):
      filhdr = filhdr_CHIME
   else:
      raise ValueError("Could not find telescope name")

   try:
      import sigproc
      filhdr['rawdatafile'] = fnfil

      newhdr = ""
      newhdr += sigproc.addto_hdr("HEADER_START", None)
      for k,v in filhdr.items():
          newhdr += sigproc.addto_hdr(k, v)
      newhdr += sigproc.addto_hdr("HEADER_END", None)
      print("Writing new header to '%s'" % fnfil)
      outfile = open(fnfil, 'wb')
      outfile.write(newhdr)
      spectrum = np.zeros([filhdr['nchans']], dtype=np.uint8)
      outfile.write(spectrum)
      outfile.close()
   except:
      print("Either could not load sigproc or create filterbank")
