# -*- coding: utf-8 -*-




from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import send_mail
import time
import datetime
from struct import *

#
## Manager
#

class RecordedDataValueManager(models.Manager):	
	def filter_time(self,time_min=None,time_max=None,**kwargs):
		'''
		
		'''
		if time_min is None:
			time_min = 0
		else:
			time_min = time_min*2097152*1000
		if time_max is None:
			time_max = time.time()*2097152*1000+2097151
		else:
			time_max = time_max*2097152*1000+2097151
		return super(RecordedDataValueManager, self).get_queryset().filter(id__range=(time_min,time_max),**kwargs)
	
	def last_element(self,**kwargs):
		'''
		
		'''
		if kwargs.has_key('time_min'):
			time_min = kwargs.pop('time_min')*2097152*1000
		else:
			time_min = (time.time()-3660)*2097152*1000 # all values will be stored once in a hour
		
		if kwargs.has_key('time_max'):
			time_max = kwargs.pop('time_max')*2097152*1000
		else:
			time_max = time.time()*2097152*1000 # values can't be more recent then now
		
		return super(RecordedDataValueManager, self).get_queryset().filter(\
				id__range=(time_min,time_max),**kwargs).last()
		
			
	def get_values_in_time_range(self,time_min=None,time_max=None,query_first_value=False,time_in_ms=False,key_is_variable_name=False,add_timetamp_field=False,add_fake_data=False,**kwargs):
		#tic = time.time()
		if time_min is None:
			time_min = 0
		else:
			db_time_min = RecordedData.objects.first()
			if db_time_min:
				db_time_min = db_time_min.timestamp
			else:
				return None
			time_min = max(db_time_min,time_min)*2097152*1000
		if time_max is None:
			time_max = time.time()*2097152*1000+2097151
		else:
			time_max = min(time_max,time.time())*2097152*1000+2097151
		values = {}
		var_filter = True
		if kwargs.has_key('variable'):
			variables = Variable.objects.filter(pk=kwargs['variable'].pk)
		elif kwargs.has_key('variable_id'):
			variables = Variable.objects.filter(pk=kwargs['variable_id'])
		elif kwargs.has_key('variable_pk__in'):
			# return all values for the given variables
			variables = Variable.objects.filter(pk__in=kwargs['variable_pk__in'])
		elif kwargs.has_key('variable_id__in'):
			# return all values for the given variables
			variables = Variable.objects.filter(pk__in=kwargs['variable_id__in'])
		elif kwargs.has_key('variable__in'):
			# return all values for the given variables
			variables = kwargs['variable__in']
		else:
			variables = Variable.objects.all()
			var_filter = False
		# export in seconds or millis
		if time_in_ms:
			f_time_scale = 1
		else:
			f_time_scale = 1000
		
		variable_ids = variables.values_list('pk',flat=True)
		# only filter by variable wenn less the 70% of all variables are queried
		if len(variable_ids) > Variable.objects.count()*0.7:
			var_filter = False
		
		tmp_time_max = 0           # get the most recent time value
		if time_in_ms:
			tmp_time_min = time.time()*1000 #
		else:
			tmp_time_min = time.time() #
		#print '%1.3fs'%(time.time()-tic)
		#tic = time.time()
		#for var in variables:
		time_slice = 2097152*1000*60*max(60,min(24*60,-3*len(variable_ids)+1440))
		query_time_min = time_min
		query_time_max = min(time_min+time_slice,time_max)
		while  query_time_min < time_max:
			if var_filter:
				tmp = list(super(RecordedDataValueManager, self).get_queryset().filter(\
					id__range=(query_time_min,min(query_time_max,time_max)),\
					variable__in=variables\
					).values_list('variable_id','pk','value_float64',\
						'value_int64','value_int32','value_int16',\
						'value_boolean'))
			else:
				tmp = list(super(RecordedDataValueManager, self).get_queryset().filter(\
					id__range=(query_time_min,min(query_time_max,time_max))\
					).values_list('variable_id','pk','value_float64',\
					'value_int64','value_int32','value_int16','value_boolean'))
	
		#	print '%1.3fs'%(time.time()-tic)
			for item in tmp:
				if item[0] not in variable_ids:
					continue
				if not values.has_key(item[0]):
					values[item[0]] = []
				tmp_time = (item[1]-item[0])/(2097152.0*f_time_scale)
				tmp_time_max = max(tmp_time,tmp_time_max)
				tmp_time_min = min(tmp_time,tmp_time_min)
				if   item[2] is not None: # float64
					values[item[0]].append([tmp_time,item[2]]) # time, value
				elif item[3] is not None: # int64
					values[item[0]].append([tmp_time,item[3]]) # time, value
				elif item[4] is not None: # int32
					values[item[0]].append([tmp_time,item[4]]) # time, value	
				elif item[5] is not None: # int16
					values[item[0]].append([tmp_time,item[5]]) # time, value	
				elif item[6] is not None: # boolean
					values[item[0]].append([tmp_time,item[6]]) # time, value
				else:
					values[item[0]].append([tmp_time,0]) # time, value
			
			del tmp
			query_time_min = query_time_max + 1
			query_time_max = query_time_min+time_slice
		#	print '%1.3fs'%(time.time()-tic)
		#	tic = time.time()
		
		# print '%1.3fs'%(time.time()-tic)
		# tic = time.time()
		# check if for all variables the first and last value is present
		update_first_value_list = []
		timestamp_max = tmp_time_max
		for key, item in values.iteritems():
			if item[-1][0] < time_max/(2097152.0*f_time_scale):
				if (time_max/(2097152.0*f_time_scale)) - item[-1][0] < 3610:
					# append last value
					item.append([time_max/(2097152.0*f_time_scale),item[-1][1]])
				
			if query_first_value and item[0][0] > time_min/(2097152.0*f_time_scale): 
				update_first_value_list.append(key)
			

		if len(update_first_value_list) > 0: #TODO add n times the recording intervall to the range (3600 + n)
			tmp = list(super(RecordedDataValueManager, self).get_queryset().filter(\
						id__range=(time_min-(3660*1000*2097152),time_min),\
						variable_id__in = update_first_value_list\
						).values_list('variable_id','pk','value_float64',\
							'value_int64','value_int32','value_int16',\
							'value_boolean'))
		
			
			first_values = {}
			for item in tmp:
				tmp_timestamp = (item[1]-item[0])/(2097152.0*f_time_scale)
				if not first_values.has_key(item[0]):
					first_values[item[0]] = [tmp_timestamp,0]
	
				if tmp_timestamp >= first_values[item[0]][0]:
					if   item[2] is not None: # float64
						first_values[item[0]][1] = item[2] # time, value
					elif item[3] is not None: # int64
						first_values[item[0]][1] = item[3] # time, value
					elif item[4] is not None: # int32
						first_values[item[0]][1] = item[4] # time, value
					elif item[5] is not None: # int16
						first_values[item[0]][1] = item[5] # time, value
					elif item[6] is not None: # boolean
						first_values[item[0]][1] = item[6] # time, value
					
			
			for key in update_first_value_list:
				if first_values.has_key(key):
					values[key].insert(0,[time_min/(2097152.0*f_time_scale),first_values[key][1]])
		#print '%1.3fs'%(time.time()-tic)
		#tic = time.time()
		
		'''
		add a datapoint bevor the next change of state
		'''
		if add_fake_data:
			for key in values:
				i = 1
				while i < len(values[key]):
					if values[key][i][0] - values[key][i-1][0] > 5: # todo add device specific delta
						values[key].insert(i,[values[key][i][0]-5,values[key][i-1][1]])
					i += 1
		'''
		change output tupple key from pk to variable name
		'''
		if key_is_variable_name:
			for item in variables:
				if values.has_key(item.pk):
					values[item.name] = values.pop(item.pk)
		'''
		add the timstamp of the most recent value
		'''
		if add_timetamp_field:
			if timestamp_max == 0:
				timestamp_max = time_min/(2097152.0*f_time_scale)
			values['timestamp'] = timestamp_max
		return values
#
## Models
#
class Color(models.Model):
	id 		= models.AutoField(primary_key=True)
	name 	= models.SlugField(max_length=80, verbose_name="variable name")
	R 		= models.PositiveSmallIntegerField(default=0)
	G 		= models.PositiveSmallIntegerField(default=0)
	B 		= models.PositiveSmallIntegerField(default=0)
	def __unicode__(self):
		return unicode('rgb('+str(self.R)+', '+str(self.G)+', '+str(self.B)+', '+')')
	def color_code(self):
		return unicode('#%02x%02x%02x' % (self.R, self.G, self.B))
	def color_rect_html(self):
		return unicode('<div style="width:4px;height:0;border:5px solid #%02x%02x%02x;overflow:hidden"></div>'% (self.R, self.G, self.B))
	
class Device(models.Model):
	id 				= models.AutoField(primary_key=True)
	short_name		= models.CharField(max_length=400, default='')
	device_type_choices = (	('generic','no Protocol'),\
							('systemstat','Local System Monitoring',),\
							('modbus','Modbus Device',),\
							('smbus','SMBus/I2C Device',),\
							('phant','Phant Device',),\
							('visa','VISA Device',),)
							
	device_type		= models.CharField(default='generic',choices=device_type_choices,max_length=400)
	description 	= models.TextField(default='', verbose_name="Description",null=True)
	active			= models.BooleanField(default=True)
	byte_order_choices = (
						('1-0-3-2','1-0-3-2'),
						('0-1-2-3','0-1-2-3'),
						('2-3-0-1','2-3-0-1'),
						('3-2-1-0','3-2-1-0'),
						)
	byte_order      = models.CharField(max_length=15, default='1-0-3-2', choices=byte_order_choices)
	polling_interval_choices = (
								(1.0  , '1 Second'),
								(5.0  , '5 Seconds'),
								(10.0 , '10 Seconds'),
								(15.0 , '15 Seconds'),
								(30.0 , '30 Seconds'),
								(60.0 , '1 Minute'),
								(150.0, '2.5 Mintues'),
								(300.0, '5 Minutes'),
								(360.0, '6 Minutes (10 times per Hour)'),
								(600.0, '10 Minutes'),
								(900.0, '15 Minutes'),
								(1800.0, '30 Minutes'),
								(3600.0, '1 Hour'),
								)
	polling_interval = models.FloatField(default= 5,choices=polling_interval_choices)
	def __unicode__(self):
		return unicode(self.short_name)

	def get_device_instance(self):
		from pyscada.modbus.device import Device as ModbusDevice
		from pyscada.systemstat.device import Device as SystemStatDevice
		from pyscada.visa.device import Device as VisaDevice
		if self.device_type == 'systemstat':
			return SystemStatDevice(self)
		elif self.device_type == 'modbus' and hasattr(self,'modbusdevice'):
			return ModbusDevice(self)
		elif self.device_type == 'visa' and hasattr(self,'visadevice'):
			return VisaDevice(self)

class Unit(models.Model):
	id 				= models.AutoField(primary_key=True)
	unit			= models.CharField(max_length=80, verbose_name="Unit")
	description 	= models.TextField(default='', verbose_name="Description",null=True)
	udunit			= models.CharField(max_length=500, verbose_name="udUnit",default='')
	def __unicode__(self):
		return unicode(self.unit)
	class  Meta:
		managed=True

class Scaling(models.Model):
	id 				= models.AutoField(primary_key=True)
	description 	= models.TextField(default='', verbose_name="Description",null=True,blank=True)
	input_low		= models.FloatField()
	input_high		= models.FloatField()
	output_low		= models.FloatField()
	output_high		= models.FloatField()
	limit_input     = models.BooleanField()
	
	def __unicode__(self):
		if self.description:
			return unicode(self.description)
		else:
			return unicode(str(self.id) + '_[' + str(self.input_low) + ':' + \
					str(self.input_high) + '] -> [' + str(self.output_low) + ':'\
					+ str(self.output_low) + ']')
	
	def scale_value(self,input_value):
		input_value = float(input_value)
		if self.limit_input:
			input_value = max(min(input_value,self.input_high),self.input_low)
		norm_value = (input_value - self.input_low)/(self.input_high - self.input_low)
		return norm_value * (self.output_high - self.output_low) + self.output_low
	
	def scale_output_value(self,input_value):
		input_value = float(input_value)
		norm_value = (input_value - self.output_low)/(self.output_high - self.output_low)
		return norm_value * (self.input_high - self.input_low) + self.input_low

class VariableProperty(models.Model):
	id 				= models.AutoField(primary_key=True)
	variable	 		= models.ForeignKey('Variable')
	property_class_choices = (	(None,'other or no Class specified'),
								('device','Device Property'),
								('data_record','Recorded Data'),
								('daemon','Daemon Property'),
							)
	property_class  = models.CharField(default=None,blank=True,null=True,max_length=255,choices=property_class_choices)
	name            = models.CharField(default='',blank=True,max_length = 255)
	value_boolean   = models.BooleanField(default=False,blank=True)  	# boolean
	value_int16     = models.SmallIntegerField(null=True,blank=True) 	# int16, uint8, int8
	value_int32     = models.IntegerField(null=True,blank=True)  		# uint8, int16, uint16, int32
	value_int64     = models.BigIntegerField(null=True,blank=True) 		# uint32, int64
	value_float64 	= models.FloatField(null=True,blank=True) 	 		# float64
	value_string    = models.CharField(default='',blank=True,max_length = 255)
	timestamp 		= models.DateTimeField(blank=True,null=True)


class Variable(models.Model):
	id 				= models.AutoField(primary_key=True)
	name 			= models.SlugField(max_length=80, verbose_name="variable name",unique=True)
	description 		= models.TextField(default='', verbose_name="Description")
	device			= models.ForeignKey(Device)
	active			= models.BooleanField(default=True)
	unit 			= models.ForeignKey(Unit,on_delete=models.SET(1))
	writeable		= models.BooleanField(default=False)
	value_class_choices = (('FLOAT32','REAL (FLOAT32)'),
						('FLOAT32','SINGLE (FLOAT32)'),
						('FLOAT32','FLOAT32'),
						('UNIXTIMEF32','UNIXTIMEF32'),
						('FLOAT64','LREAL (FLOAT64)'),
						('FLOAT64','FLOAT  (FLOAT64)'),
						('FLOAT64','DOUBLE (FLOAT64)'),
						('FLOAT64','FLOAT64'),
						('UNIXTIMEF64','UNIXTIMEF64'),
						('INT64','INT64'),
						('UINT64','UINT64'),
						('UNIXTIMEI64','UNIXTIMEI64'),
						('UNIXTIMEI32','UNIXTIMEI32'),
						('INT32','INT32'),
						('UINT32','DWORD (UINT32)'),
						('UINT32','UINT32'),
						('INT16','INT (INT16)'),
						('INT16','INT16'),
						('UINT16','WORD (UINT16)'),
						('UINT16','UINT (UINT16)'),
						('UINT16','UINT16'),
						('BOOLEAN','BOOL (BOOLEAN)'),
						('BOOLEAN','BOOLEAN'),
						)
	scaling			= models.ForeignKey(Scaling,null=True,blank=True, on_delete=models.SET_NULL)
	value_class		= models.CharField(max_length=15, default='FLOAT64', verbose_name="value_class",choices=value_class_choices)
	cov_increment   = models.FloatField(default=0,blank=True)
	byte_order_choices = (('default','default (specified by device byte order)',),
						('1-0-3-2','1-0-3-2'),
						('0-1-2-3','0-1-2-3'),
						('2-3-0-1','2-3-0-1'),
						('3-2-1-0','3-2-1-0'),
						)
	short_name			= models.CharField(default='',max_length=80, verbose_name="variable short name",blank=True)
	chart_line_color 	= models.ForeignKey(Color,null=True,default=None,blank=True)
	chart_line_thickness_choices = ((3,'3Px'),)
	chart_line_thickness = models.PositiveSmallIntegerField(default=3,choices=chart_line_thickness_choices)
	def hmi_name(self):
		if self.short_name and self.short_name != '-' and self.short_name != '':
			return self.short_name
		else:
			return self.name
	
	def chart_line_color_code(self):
		if self.chart_line_color and self.chart_line_color.id != 1:
			return self.chart_line_color.color_code()
		else:
			c = 51
			id = self.pk+1
			c = c%id
			while c >= 51:
				id = id-c
				c = c%id
			return Color.objects.get(id=id).color_code()
	
	'''
	M: Mantissia
	E: Exponent
	S: Sign
			uint 0            uint 1 
			byte 0   byte 1   byte 2   byte 3
	1-0-3-2 MMMMMMMM MMMMMMMM SEEEEEEE EMMMMMMM
	0-1-2-3 MMMMMMMM MMMMMMMM EMMMMMMM SEEEEEEE
	2-3-0-1 EMMMMMMM SEEEEEEE MMMMMMMM MMMMMMMM
	3-2-1-0 SEEEEEEE EMMMMMMM MMMMMMMM MMMMMMMM
	'''
	byte_order      = models.CharField(max_length=15, default='default', choices=byte_order_choices)
	# for RecodedVariable
	value           	= None
	prev_value 		= None
	store_value 		= False		
	timestamp_old   = None
	timestamp       = None

	def __unicode__(self):
		return unicode(self.name)
	
	def add_attr(self,**kwargs):
		for key in kwargs:
			setattr(self,key,kwargs[key])
	
	def get_bits_by_class(self):
		"""
		`BOOLEAN`							1	1/16 WORD
		`UINT8` `BYTE`						8	1/2 WORD
		`INT8`								8	1/2 WORD
		`UNT16` `WORD`						16	1 WORD
		`INT16`	`INT`						16	1 WORD
		`UINT32` `DWORD`					32	2 WORD
		`INT32`								32	2 WORD
		`FLOAT32` `REAL` `SINGLE` 			32	2 WORD
		`FLOAT64` `LREAL` `FLOAT` `DOUBLE`	64	4 WORD
		"""
		if 	self.value_class.upper() in ['FLOAT64','DOUBLE','FLOAT','LREAL','UNIXTIMEI64','UNIXTIMEF64'] :
			return 64
		if 	self.value_class.upper() in ['FLOAT32','SINGLE','INT32','UINT32','DWORD','BCD32','BCD24','REAL','UNIXTIMEI32','UNIXTIMEF32'] :
			return 32
		if self.value_class.upper() in ['INT16','INT','WORD','UINT','UINT16','BCD16']:
			return 16
		if self.value_class.upper() in ['INT8','UINT8','BYTE','BCD8']:
			return 8
		if self.value_class.upper() in ['BOOL','BOOLEAN']:
			return 1
		else:
			return 16
	
	def query_prev_value(self):
		'''
		get the las value and timestamp from the database
		'''
		time_max = time.time()*2097152*1000+2097151
		val = self.recordeddata_set.filter(id__range=(time_max-(3660*1000*2097152),time_max)).last()
		if val:
			self.prev_value = val.value()
			self.timestamp_old = val.timestamp
			return True
		else:
			return False
	
	def update_value(self,value = None,timestamp=None):
		'''
		update the value in the instance and detect value state change
		'''
		
		if self.scaling is None or value is None or self.value_class.upper() in ['BOOL','BOOLEAN']:
			self.value =  value
		else:
			self.value =  self.scaling.scale_value(value)
		self.timestamp = timestamp
		self.store_value = False
		if self.prev_value is None:
			# no prev value in the cache, always store the value
			self.store_value = True
			self.timestamp_old = self.timestamp
		elif self.value is None:
			# value could not be queried
			self.store_value = False
		elif abs(self.prev_value - self.value) <= self.cov_increment:
			if self.timestamp_old is None:
				self.store_value = True
				self.timestamp_old = self.timestamp
			else:
				if (self.timestamp - self.timestamp_old) >= (3600): 
					# store at least every hour one value
					# store Value if old Value is older then 1 hour
					self.store_value = True
					self.timestamp_old = self.timestamp
				
		else:                               
			# value has changed
			self.store_value = True
			self.timestamp_old = self.timestamp
		self.prev_value = self.value
		return self.store_value
	
	def decode_value(self,value):
		# 
		if self.byte_order == 'default':
			byte_order = self.device.byte_order
		else:
			byte_order = self.byte_order
		
		if 	self.value_class.upper() in ['FLOAT32','SINGLE','REAL','UNIXTIMEF32']:
			target_format = 'f'
			source_format = '2H'
		elif self.value_class.upper() in ['UINT32','DWORD','UNIXTIMEI32']:
			target_format = 'I'
			source_format = '2H'
		elif self.value_class.upper() in ['INT32']:
			target_format = 'i'
			source_format = '2H'
		elif 	self.value_class.upper() in ['FLOAT64','DOUBLE','FLOAT','LREAL','UNIXTIMEF64']:
			target_format = 'd'
			source_format = '4H'
		elif self.value_class.upper() in ['UINT64']:
			target_format = 'Q'
			source_format = '4H'
		elif self.value_class.upper() in ['INT64','UNIXTIMEI64']:
			target_format = 'q'
			source_format = '4H'
		elif self.value_class.upper() in ['INT16','INT']:
			if byte_order in ['1-0-3-2','3-2-1-0']:
				# only convert to from uint to int
				return unpack('h',pack('H',value[0]))[0]
			else:
				# swap bytes
				return unpack('>h',pack('<H',value[0]))[0]
		elif self.value_class.upper() in ['BCD32','BCD24','BCD16']:
			target_format = 'f'
			source_format = '2H'
			return value[0]
		else:
			return value[0]
		
		#
		if source_format == '2H':
			if byte_order == '1-0-3-2':
				return unpack(target_format,pack(source_format,value[0],value[1]))[0]
			if byte_order == '3-2-1-0':
				return unpack(target_format,pack(source_format,value[1],value[0]))[0]
			if byte_order == '0-1-2-3':
				return unpack(target_format,pack(source_format,unpack('>H',pack('<H',value[0])),unpack('>H',pack('<H',value[1]))))[0]
			if byte_order == '2-3-0-1':
				return unpack(target_format,pack(source_format,unpack('>H',pack('<H',value[1])),unpack('>H',pack('<H',value[0]))))[0]	
		else:
			if byte_order == '1-0-3-2':
				return unpack(target_format,pack(source_format,value[0],value[1],value[2],value[3]))[0]
			if byte_order == '3-2-1-0':
				return unpack(target_format,pack(source_format,value[3],value[2],value[1],value[0]))[0]
			if byte_order == '0-1-2-3':
				return unpack(target_format,pack(source_format,unpack('>H',pack('<H',value[0])),unpack('>H',pack('<H',value[1])),unpack('>H',pack('<H',value[2])),unpack('>H',pack('<H',value[3]))))[0]
			if byte_order == '2-3-0-1':
				return unpack(target_format,pack(source_format,unpack('>H',pack('<H',value[3])),unpack('>H',pack('<H',value[2])),unpack('>H',pack('<H',value[1])),unpack('>H',pack('<H',value[0]))))[0]	
	
	def encode_value(self,value):
		if 	self.value_class.upper() in ['FLOAT32','SINGLE','REAL','UNIXTIMEF32']:
			source_format = 'f'
			target_format = '2H'
		elif self.value_class.upper() in ['UINT32','DWORD','UNIXTIMEI32']:
			source_format = 'I'
			target_format = '2H'
		elif self.value_class.upper() in ['INT32']:
			source_format = 'i'
			target_format = '2H'
		
		elif 	self.value_class.upper() in ['FLOAT64','DOUBLE','FLOAT','LREAL','UNIXTIMEF64']:
			source_format = 'd'
			target_format = '4H'
		elif self.value_class.upper() in ['UINT64']:
			source_format = 'Q'
			target_format = '4H'
		elif self.value_class.upper() in ['INT64','UNIXTIMEI64']:
			source_format = 'q'
			target_format = '4H'
		
		elif 	self.value_class.upper() in ['BCD32','BCD24','BCD16']:
			source_format = 'f'
			target_format = '2H'
			return value[0]
		else:
			return value[0]
		output = unpack(target_format,pack(source_format,value))
		# 
		if self.byte_order == 'default':
			byte_order = self.device.byte_order
		else:
			byte_order = self.byte_order
		if source_format == '2H':
			if byte_order == '1-0-3-2':
				return output
			if byte_order == '3-2-1-0':
				return [output[1],output[0]]
			if byte_order == '0-1-2-3':
				return [unpack('>H',pack('<H',output[0])),unpack('>H',pack('<H',output[1]))]
			if byte_order == '2-3-0-1':
				return [unpack('>H',pack('<H',output[1])),unpack('>H',pack('<H',output[0]))]
		else:
			if byte_order == '1-0-3-2':
				return output
			if byte_order == '3-2-1-0':
				return [output[3],output[2],output[1],output[0]]
			if byte_order == '0-1-2-3':	
				return [unpack('>H',pack('<H',output[0])),unpack('>H',pack('<H',output[1])),unpack('>H',pack('<H',output[2])),unpack('>H',pack('<H',output[3]))]
			if byte_order == '2-3-0-1':
				return [unpack('>H',pack('<H',output[3])),unpack('>H',pack('<H',output[2])),unpack('>H',pack('<H',output[1])),unpack('>H',pack('<H',output[0]))]
		
	
	
	def create_recorded_data_element(self):
		'''
		create a new element to write to archive table
		'''
		if self.store_value and not self.value is None:
			return RecordedData(timestamp=self.timestamp,variable=self,value=self.value)
		else:
			return None

class DeviceWriteTask(models.Model):
	id 				= models.AutoField(primary_key=True)
	variable	 		= models.ForeignKey('Variable')
	value			= models.FloatField()
	user	 		= models.ForeignKey(User,null=True, on_delete=models.SET_NULL)
	start 			= models.FloatField(default=0) #TODO DateTimeField
	fineshed			= models.FloatField(default=0,blank=True) #TODO DateTimeField
	done			= models.BooleanField(default=False,blank=True)
	failed			= models.BooleanField(default=False,blank=True)


class RecordedData(models.Model):
	# Big Int first 42 bis is used for unixtime in ms, unsigt because we only 
	# store time values that are later then 1970, rest 21 bits for the 
	# variable id to have a uniqe primary key
	# 63 bit 111111111111111111111111111111111111111111111111111111111111111
	# 42 bit 111111111111111111111111111111111111111111000000000000000000000
	# 21 bit 										  1000000000000000000000

	id				= models.BigIntegerField(primary_key=True)
	value_boolean   = models.BooleanField(default=False,blank=True)  	# boolean
	value_int16     = models.SmallIntegerField(null=True,blank=True) 	# int16, uint8, int8
	value_int32     = models.IntegerField(null=True,blank=True)  		# uint8, int16, uint16, int32
	value_int64     = models.BigIntegerField(null=True,blank=True) 		# uint32, int64
	value_float64 	= models.FloatField(null=True,blank=True) 	 		# float64
	variable		= models.ForeignKey('Variable')
	objects 		= RecordedDataValueManager()
	
	def __init__(self, *args, **kwargs):
		if kwargs.has_key('timestamp'):
			timestamp = kwargs.pop('timestamp')
		else:
			timestamp = time.time()
		if kwargs.has_key('variable_id'):
			variable_id = kwargs['variable_id']
		elif kwargs.has_key('variable'):
			variable_id = kwargs['variable'].pk
		else:
			variable_id = None
		if not variable_id is None and not kwargs.has_key('id'):
			kwargs['id'] = int(int(int(timestamp*1000)*2097152)+variable_id)
		if kwargs.has_key('variable') and kwargs.has_key('value'):
			if kwargs['variable'].value_class.upper() in ['FLOAT','FLOAT64','DOUBLE','FLOAT32','SINGLE','REAL']:
				kwargs['value_float64'] = float(kwargs.pop('value'))
			elif kwargs['variable'].scaling and not kwargs['variable'].value_class.upper() in ['BOOL','BOOLEAN']:
				kwargs['value_float64'] = float(kwargs.pop('value'))
			elif kwargs['variable'].value_class.upper() in ['INT64','UINT32','DWORD']:
				kwargs['value_int64'] = int(kwargs.pop('value'))
				if kwargs['value_int64'].bit_length() > 64:
					#todo throw exeption or do anything
					pass
			elif kwargs['variable'].value_class.upper() in ['WORD','UINT','UINT16','INT32']:
				kwargs['value_int32'] = int(kwargs.pop('value'))
				if kwargs['value_int32'].bit_length() > 32:
					#todo throw exeption or do anything
					pass
			elif kwargs['variable'].value_class.upper() in ['INT16','INT8','UINT8','INT']:
				kwargs['value_int16'] = int(kwargs.pop('value'))
				if kwargs['value_int16'].bit_length() > 15:
					#todo throw exeption or do anything
					pass
				
			elif kwargs['variable'].value_class.upper() in ['BOOL','BOOLEAN']:
				kwargs['value_boolean'] = bool(kwargs.pop('value'))
				
		# call the django model __init__
		super(RecordedData, self).__init__(*args, **kwargs)
		self.timestamp = self.time_value()
				
	def calculate_pk(self,timestamp=None):
		'''
		calculate the primary key from the timestamp in seconds
		'''
		if timestamp is None:
			timestamp = time.time()
		self.pk = int(int(int(timestamp*1000)*2097152)+self.variable.pk)

	def __unicode__(self):
		return unicode(self.value())

	def time_value(self):
		'''
		return the timestamp in seconds calculated from the id
		'''
		return (self.pk-self.variable.pk)/2097152/1000.0 # value in seconds 

	def value(self,value_class=None):
		'''
		return the stored value
		'''
		if value_class is None:
			value_class = self.variable.value_class
		
			
		if value_class.upper() in ['FLOAT','FLOAT64','DOUBLE','FLOAT32','SINGLE','REAL']:
			return self.value_float64
		elif self.variable.scaling and not value_class.upper() in ['BOOL','BOOLEAN']:
			return self.value_float64
		elif value_class.upper() in ['INT64','UINT32','DWORD']:
			return self.value_int64
		elif value_class.upper() in ['WORD','UINT','UINT16','INT32']:
			return self.value_int32
		elif value_class.upper() in ['INT16','INT8','UINT8']:
			return self.value_int16
		elif value_class.upper() in ['BOOL','BOOLEAN']:
			return self.value_boolean
		else:
			return None


class Log(models.Model):
	#id 				= models.AutoField(primary_key=True)
	id				= models.BigIntegerField(primary_key=True)
	level			= models.IntegerField(default=0, verbose_name="level")
	timestamp 		= models.FloatField()#TODO DateTimeField
	message_short	= models.CharField(max_length=400, default='', verbose_name="short message")
	message 		= models.TextField(default='', verbose_name="message")
	user	 		= models.ForeignKey(User,null=True, on_delete=models.SET_NULL)
	def __init__(self, *args, **kwargs):
		if kwargs.has_key('timestamp'):
			timestamp = kwargs['timestamp']
		else:
			timestamp = time.time()
			kwargs['timestamp'] = timestamp
		if not kwargs.has_key('id'):
			if kwargs.has_key('level'):
				kwargs['id'] = int(int(int(timestamp*1000)*2097152)+kwargs['level'])
			else:
				kwargs['id'] = int(int(int(timestamp*1000)*2097152)+0)
		super(Log, self).__init__(*args, **kwargs)
	
	def __unicode__(self):
		return unicode(self.message)


class BackgroundTask(models.Model):
	id 				= models.AutoField(primary_key=True)
	start 			= models.FloatField(default=0)#TODO DateTimeField
	timestamp 		= models.FloatField(default=0)#TODO DateTimeField
	progress		    = models.FloatField(default=0)
	load			= models.FloatField(default=0)
	min 			= models.FloatField(default=0)
	max				= models.FloatField(default=0)
	done			= models.BooleanField(default=False,blank=True)
	failed			= models.BooleanField(default=False,blank=True)
	pid				= models.IntegerField(default=0)
	stop_daemon		= models.BooleanField(default=False,blank=True)
	restart_daemon  = models.BooleanField(default=False,blank=True)
	label			= models.CharField(max_length=400, default='')
	message			= models.CharField(max_length=400, default='')
	identifier      = models.CharField(max_length=400, default='',blank=True)

	def __unicode__(self):
		return unicode(self.timestamp)
	def timestamp_ms(self):
		return self.timestamp * 1000

	
class Event(models.Model):
	id 				= models.AutoField(primary_key=True)
	label			= models.CharField(max_length=400, default='')
	variable    		= models.ForeignKey(Variable)
	level_choices	= 	(
							(0,'informative'),
							(1,'ok'),
							(2,'warning'),
							(3,'alert'),
						)
	level			= models.PositiveSmallIntegerField(default=0,choices=level_choices)
	fixed_limit		= models.FloatField(default=0,blank=True,null=True)
	variable_limit  = models.ForeignKey(Variable,blank=True,null=True,default=None, on_delete=models.SET_NULL,related_name="variable_limit",help_text="you can choose either an fixed limit or an variable limit that is dependent on the current value of an variable, if you choose a value other then none for varieble limit the fixed limit would be ignored")
	limit_type_choices = 	(
								(0,'value is less than limit',),
								(1,'value is less than or equal to the limit',),
								(2,'value is greater than the limit'),
								(3,'value is greater than or equal to the limit'),
								(4,'value equals the limit'),
							)
	limit_type		= models.PositiveSmallIntegerField(default=0,choices=limit_type_choices)
	hysteresis      = models.FloatField(default=0,blank=True)
	action_choices	= 	(
							(0,'just record'),
							(1,'record and send mail only wenn event occurs'),
							(2,'record and send mail'),
							(3,'record, send mail and change variable'),
						)
	action				= models.PositiveSmallIntegerField(default=0,choices=action_choices)
	mail_recipients		= models.ManyToManyField(User)
	variable_to_change  = models.ForeignKey(Variable,blank=True,null=True,default=None, on_delete=models.SET_NULL,related_name="variable_to_change")
	new_value			= models.FloatField(default=0,blank=True,null=True)
	def __unicode__(self):
		return unicode(self.label)

	def do_event_check(self):
		'''
		
		compair the actual value with the limit value
		
		(0,'value is below the limit',),
		(1,'value is less than or equal to the limit',),
		(2,'value is greater than the limit'),
		(3,'value is greater than or equal to the limit'),
		(4,'value equals the limit'),
		'''
		def compose_mail(active):
			if hasattr(settings,'EMAIL_SUBJECT_PREFIX'):
				subject = settings.EMAIL_SUBJECT_PREFIX
			else:
				subject = ''
			
			message = ''
			if active:
				if   self.level == 0: # infomation
					subject += " Infomation "
				elif self.level == 1: # Ok
					subject += " "
				elif self.level == 2: # warning
					subject += " Warning! "	
				elif self.level == 3: # alert
					subject += " Alert! "
				subject += self.variable.name + " has exceeded the limit"
			else:
				subject += " Infomation "
				subject += self.variable.name + " is back in limit"
			message = "The Event " + self.label + " has been triggert\n"
			message += "Value of " + self.variable.name + " is " + actual_value.__str__() + " " + self.variable.unit.unit
			message += " Limit is " + limit_value.__str__() + " " + self.variable.unit.unit
			return (subject,message,)
		# 
		# get recorded event
		prev_event = RecordedEvent.objects.filter(event=self,active=True)
		if prev_event:
			prev_value = True
		else:
			prev_value = False
		# get the actual value
		#actual_value = RecordedDataCache.objects.filter(variable=self.variable).last() # TODO change to RecordedData 
		actual_value = RecordedData.objects.last_element(variable=self.variable)
		if not actual_value:
			return False
		timestamp = actual_value.time_value()
		actual_value = actual_value.value()
		# determin the limit type, variable or fixed
		if self.variable_limit:
			# item has a variable limit
			# get the limit value
			#limit_value = RecordedDataCache.objects.filter(variable=self.variable_limit) # TODO change to RecordedData
			limit_value = RecordedData.objects.last_element(variable=self.variable_limit)
			if not limit_value:
				return False
			if timestamp < limit_value.last().time_value():
				# wenn limit value has changed after the actual value take that time
				timestamp = limit_value.last().time_value()
			limit_value = limit_value.last().value() # get value
		else:
			# item has a fixed limit
			limit_value = self.fixed_limit
	
		if self.limit_type == 0:
			if prev_value:
				limit_check = actual_value < (limit_value + self.hysteresis)
			else:
				limit_check = actual_value < (limit_value - self.hysteresis)
		elif self.limit_type == 1:
			if prev_value:
				limit_check = actual_value <= (limit_value + self.hysteresis)
			else:
				limit_check = actual_value <= (limit_value - self.hysteresis)
		elif self.limit_type == 2:
			limit_check = actual_value <= limit_value + self.hysteresis and actual_value >= limit_value - self.hysteresis
		elif self.limit_type == 3:
			if prev_value:
				limit_check = actual_value >= (limit_value - self.hysteresis)
			else:
				limit_check = actual_value >= (limit_value + self.hysteresis)
		elif self.limit_type == 4:
			if prev_value:
				limit_check = actual_value > (limit_value - self.hysteresis)
			else:
				limit_check = actual_value > (limit_value + self.hysteresis)
		else:
			return False
		
		# record event
		if limit_check: # value is outside of the limit
			if not prev_event:
				# if there is no previus event record the Event
				prev_event = RecordedEvent(event = self,time_begin=timestamp,active=True)
				prev_event.save()

				if self.limit_type >= 1:
					# compose and send mail
					(subject,message,) = compose_mail(True)
					for recipient in self.mail_recipients.exclude(email=''):
						Mail(None,subject,message,recipient.email,time.time()).save()
				
				if self.limit_type >= 3:
					# do action
					if self.variable_to_change:
						DeviceWriteTask(variable=self.variable_to_change,value=self.new_value,start=timestamp)
		else: # back inside of limit
			if prev_event: # 
				prev_event = prev_event.last()
				prev_event.active = False
				prev_event.time_end = timestamp
				prev_event.save()
				
				if self.limit_type >= 2:
					# compose and send mail
					(subject,message,) = compose_mail(False)
					for recipient in self.mail_recipients.exclude(email=''):
						Mail(None,subject,message,recipient.email,time.time()).save()


class RecordedEvent(models.Model):
	id          = models.AutoField(primary_key=True)
	event		= models.ForeignKey(Event)
	time_begin  = models.FloatField(default=0) #TODO DateTimeField
	time_end	= models.FloatField(null=True,blank=True) #TODO DateTimeField
	active		= models.BooleanField(default=False,blank=True)


class Mail(models.Model):
	id 			= models.AutoField(primary_key=True)
	subject     = models.TextField(default='',blank=True)
	message     = models.TextField(default='',blank=True)
	to_email	= models.EmailField(max_length=254)
	timestamp 	= models.FloatField(default=0,blank=True) #TODO DateTimeField
	done		= models.BooleanField(default=False,blank=True)
	send_fail_count = models.PositiveSmallIntegerField(default=0,blank=True)
	def send_mail(self):
		# TODO check email limit
		# blocked_recipient = [] # list of blocked mail recipoients
		# mail_count_limit = 200 # send max 200 Mails per 24h per user
		# 	
		# for recipient in mail.mail_recipients.exclude(to_email__in=blocked_recipient):
		# 	if recipient.mail_set.filter(timestamp__gt=time()-(60*60*24)).count() > self.mail_count_limit:
		# 		blocked_recipient.append(recipient.pk)
		if self.send_fail_count >= 3 or self.done: 
			# only try to send an email three times
			return False
		# send the mail
		if send_mail(self.subject,self.message,settings.DEFAULT_FROM_EMAIL,[self.to_email],fail_silently=True):
			self.done       = True
			self.timestamp  = time.time()
			self.save()
			return True
		else:
			self.send_fail_count = self.send_fail_count + 1
			self.timestamp  = time.time()
			self.save()
			return False


@receiver(post_save, sender=Variable)
@receiver(post_save, sender=Device)
@receiver(post_save, sender=Scaling)
def _reinit_daq_daemons(sender, **kwargs):
	"""
	update the daq daemon configuration wenn changes be applied in the models
	"""
	bt = BackgroundTask.objects.filter(label='pyscada.daq.daemon',done=0,failed=0).update(message='reinit',restart_daemon=True,timestamp = time.time())
