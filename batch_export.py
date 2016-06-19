#!/usr/bin/env python
# -*- encoding=utf-8 -*-
# batch export lua files

import re
import os
import sys
import pickle
import commands
import datetime
import threading

from os.path import join
from datetime import datetime

class BatchExportLua:
    def __init__(self, rootdir):
        if not os.path.exists(rootdir):
            print >> sys.stderr, 'invalid path: {}'.format(rootdir)
            sys.exit(1)

        os.chdir(rootdir)
        self.__pardir = os.path.abspath(os.pardir)

        self.__mtime_dict_file = '_mtime_dict_file'

        # load the mtime_dict from file
        if not os.path.exists(self.__mtime_dict_file) \
                or os.path.getsize(self.__mtime_dict_file) == 0:
            self.__mtime_dict = {}
        else:
            dict_file = open(self.__mtime_dict_file, 'rb')
            self.__mtime_dict = pickle.load(dict_file)
            dict_file.close()

        # compile regrex patterns
        # python ../../../server_tools/export_lua.py \
        #       ../../../excels/config/guild/guildconf.xls \
        #       ../../../server_tools/json/guild/guildconf.json \
        #       ../../../data/config/guild/guild.lua
        self.__split_args_re = re.compile(r'\s*python\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*')

        # old version export python tool
        # python ../../../python/lua_table_generator.py -f ../../../excels/config/buff/buffconf.xls \
        #        -o ../../../data/config/buff
        self.__split_old_ver_args_re = re.compile(r'\s*python\s+(\S+)\s+-f\s+(\S+)\s+-o\s+(\S+)\s*')

        # ../../../excels/config/guild/guildconf.xls
        self.__extract_filename_withbasedir_re = re.compile(r'(?:\.\./)+(\S+)')

        # excels set
        self.__new_excels = set()
        self.__skip_excels = set()

        # success output lua files set
        self.__success_output_luas = {}
        self.__success_output_luas_mutex = threading.Lock()

        # failure output lua files set
        self.__failure_output_luas = {}
        self.__failure_output_luas_mutex = threading.Lock()

        # time
        self.__starttime = None
        self.__endtime = None

        # threads
        self.__threads = []

    def __export(self, python_file, excel_file, json_file, lua_file):
        cmd = 'python ' + python_file + ' ' + excel_file + ' ' + json_file + ' ' + lua_file

        status, result = commands.getstatusoutput(cmd)

        lua_file_relative_path = lua_file[lua_file.rfind('../') + 3:]

        if status == 0:
            self.__success_output_luas_mutex.acquire()
            self.__success_output_luas[lua_file_relative_path] = result
            self.__success_output_luas_mutex.release()
        else:
            self.__failure_output_luas_mutex.acquire()
            self.__failure_output_luas[lua_file_relative_path] = result
            self.__failure_output_luas_mutex.release()

    def __scan_file(self, filename):
        ext_name = os.path.splitext(filename)[1]
        if not ext_name in ['.bat', '.bat1']:
            return

        fi = open(filename, 'r')

        for line in fi.readlines():
            args = self.__split_old_ver_args_re.findall(line)
            args = args[0] if len(args) > 0 else ''
            if len(args) == 3:
                new_ver = False
            else:
                args = self.__split_args_re.findall(line)
                args = args[0] if len(args) > 0 else ''
                if len(args) == 4:
                    new_ver = True
                else:
                    continue

            excel_file = join(self.__pardir, self.__extract_filename_withbasedir_re.findall(args[1])[0])
            excel_mtime = os.stat(excel_file).st_mtime

            if new_ver:
                json_file = join(self.__pardir, self.__extract_filename_withbasedir_re.findall(args[2])[0])
                json_mtime = os.stat(json_file).st_mtime

            skip = False
            if excel_file in self.__new_excels:                         # new ?
                if new_ver:
                    self.__mtime_dict[json_file] = json_mtime

            elif self.__mtime_dict.has_key(excel_file):
                if self.__mtime_dict[excel_file] >= excel_mtime: # old ?
                    if new_ver: # old ?
                        dict_json_mtime = self.__mtime_dict.get(json_file) 
                        if json_mtime is not None and dict_json_mtime >= json_mtime:
                            skip = True
                            self.__skip_excels.add(excel_file)
                        else:
                            self.__mtime_dict[json_file] = json_mtime
                    else:
                        skip = True
                        self.__skip_excels.add(excel_file)
                else:                                                   # newer ?
                    self.__new_excels.add(excel_file)
                    self.__mtime_dict[excel_file] = excel_mtime

                    if new_ver:
                        self.__mtime_dict[json_file] = json_mtime
            else:
                self.__new_excels.add(excel_file)                       # add new excel
                self.__mtime_dict[excel_file] = excel_mtime

                if new_ver:
                    self.__mtime_dict[json_file] = json_mtime

            if skip:
                continue

            python_file = join(self.__pardir, self.__extract_filename_withbasedir_re.findall(args[0])[0])

            if new_ver:
                #  json_file = join(self.__pardir, self.__extract_filename_withbasedir_re.findall(args[2])[0])
                lua_file = join('..', self.__extract_filename_withbasedir_re.findall(args[3])[0])
            else:
                excel_file = '-f ' + excel_file
                json_file = '-o'
                lua_file = join('..', self.__extract_filename_withbasedir_re.findall(args[2])[0])

            # start an new thread to export lua_file
            th = threading.Thread(target=self.__export, args=(python_file, excel_file, json_file, lua_file))
            th.start()
            self.__threads.append(th)

        fi.close()

    def __scan_dir(self, dirname):
        old_dir = os.getcwd()
        os.chdir(dirname)

        files = os.listdir('.')
        for f in files:
            if os.path.isdir(f):
                self.__scan_dir(f)
            else:
                self.__scan_file(f)

        os.chdir(old_dir)

    def __start(self):
        self.__starttime = datetime.now()
        self.__scan_dir('./config')

    def __end(self):
        # wait for threads terminate
        for th in self.__threads:
            th.join()

       # pickle excels_mtime_dict
        dict_file = open(self.__mtime_dict_file, 'wb')
        pickle.dump(self.__mtime_dict, dict_file)
        dict_file.close()

        # record end time
        self.__endtime = datetime.now()

        # output result
        self.__output_result()

    class __OutputStream:
        def __init__(self):
            self.buff = ''
            self.console = sys.stdout # save the old stdout

        # public external call to write
        def write(self, output_stream):
            self.buff += output_stream

        # private internal call to write
        def __write(self, streamobj):
            print >> streamobj, self.buff

        def write2console(self):
            self.__write(self.console)

        def write2file(self, filename):
            of = open(filename, 'w')
            self.__write(of)
            of.close()

        def append2file(self, filename):
            of = open(filename, 'a')
            self.__write(of)
            of.close()

        def flush(self):
            self.buff = ''

        def reset(self):
            sys.stdout = self.console

    def __output_result(self):
        streamobj = self.__OutputStream()
        sys.stdout = streamobj

        # print skip excels
        print 'skip excels:'
        for filename in self.__skip_excels:
            print filename
        else:
            print '\n'

        # print new excels
        print 'new excels:'
        for filename in self.__new_excels:
            print filename
        else:
            print '\n'

        # print success_output_luas
        print 'succes output files:'
        for filename, result in self.__success_output_luas.iteritems():
            print filename, ':\n', result, '\n'
        else:
            print '\n'

        # print failure_output_luas
        print 'failure output files:'
        for filename, result in self.__failure_output_luas.iteritems():
            print filename, ':\n\t', result, '\n'
        else:
            print '\n'

        # print cost time 
        print 'cost time:'
        print '  start  {}'.format(self.__starttime)
        print '  end    {}'.format(self.__endtime)
        print '  total  {}'.format(self.__endtime - self.__starttime)

        streamobj.write2console()
        streamobj.write2file('result.txt')
        streamobj.flush()
        streamobj.reset()

    def run(self):
        self.__start()
        self.__end()

# main routine
if __name__ == '__main__':
    argv = sys.argv
    instance = BatchExportLua('.')
    instance.run()
