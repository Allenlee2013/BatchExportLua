#!/usr/bin/env python
# encoding=utf-8

import re
import os
import sys
import datetime
import threading
import commands
import pickle

from os.path import join

class BatchExportLua:
    def __init__(self, rootdir):
        if not os.path.exists(rootdir):
            print >> sys.stderr, 'invalid directory path: {}'.format(rootdir)
            sys.exit(1)

        os.chdir(rootdir)
        self.pardir = os.path.abspath(os.pardir)

        self.excels_mtime_dict_file = '_excels_mtime_dict_file'

        # create an new file first
        if not os.path.exists(self.excels_mtime_dict_file):
            print 'not exists {}'.format(self.excels_mtime_dict_file)
            open(self.excels_mtime_dict_file, 'wb').close()
            self.excels_mtime_dict = {}
        else:
            # load the mtime_dict from file
            dict_file = open(self.excels_mtime_dict_file, 'rb')
            self.excels_mtime_dict = pickle.load(dict_file)
            dict_file.close()

        # compile regrex patterns
        self.split_args_re = re.compile(r'\s*python\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s+([^\s]+)\s*')
        self.extract_filename_withbasedir_re = re.compile(r'(?:\.\./)+([^\s]+)')

        # excels set
        self.new_excels = set()
        self.skip_excels = set()
        self.output_excels = set()

        # success output lua files set
        self.success_output_luas = {}
        self.success_output_luas_mutex = threading.Lock()

        # failure output lua files set
        self.failure_output_luas = {}
        self.failure_output_luas_mutex = threading.Lock()

        # threads
        self.threads = []

    def export(self, python_file, excel_name, json_file, lua_file):
        cmd = 'python ' + python_file + ' ' + excel_name + ' ' + json_file + ' ' + lua_file

        status, result = commands.getstatusoutput(cmd)

        lua_file_relative_path = lua_file[lua_file.find('data/config'):]

        if status == 0:
            self.success_output_luas_mutex.acquire()
            self.success_output_luas[lua_file_relative_path] = result
            self.success_output_luas_mutex.release()
        else:
            self.failure_output_luas_mutex.acquire()
            self.failure_output_luas[lua_file_relative_path] = result
            self.failure_output_luas_mutex.release()

    def scan_file(self, filename):
        ext_name = os.path.splitext(filename)[1]
        if not ext_name in ['.bat']:
            return

        fi = open(filename, 'r')

        for line in fi.readlines():
            args = self.split_args_re.findall(line)
            args = len(args) > 0 and args[0] or ''
            if len(args) == 4:
                excel_name = join(self.pardir, self.extract_filename_withbasedir_re.findall(args[1])[0])

                excel_mtime = os.stat(excel_name).st_mtime

                skip = False
                if excel_name in self.new_excels:
                    pass
                elif self.excels_mtime_dict.has_key(excel_name):
                    if self.excels_mtime_dict[excel_name] >= excel_mtime:
                        skip = True
                        self.skip_excels.add(excel_name)
                else:
                    self.new_excels.add(excel_name)
                    self.excels_mtime_dict[excel_name] = excel_mtime

                if skip:
                    continue

                python_file = join(self.pardir, self.extract_filename_withbasedir_re.findall(args[0])[0])
                json_file = join(self.pardir, self.extract_filename_withbasedir_re.findall(args[2])[0])
                lua_file = join('..', self.extract_filename_withbasedir_re.findall(args[3])[0])

                # start an new thread 
                th = threading.Thread(target=self.export, args=(python_file, excel_name, json_file, lua_file))
                th.start()
                self.threads.append(th)

        fi.close()

    def scan_dir(self, dirname):
        old_dir = os.getcwd()
        os.chdir(dirname)

        files = os.listdir('.')
        for f in files:
            if os.path.isdir(f):
                self.scan_dir(f)
            else:
                self.scan_file(f)

        os.chdir(old_dir)

    def start(self):
        self.scan_dir('./config')

    def end(self):
        # wait for threads terminate
        for th in self.threads:
            th.join()

        # print success_output_luas
        print 'succes output files:'
        for filename, result in self.success_output_luas.iteritems():
            print filename, ':\n\t', result, '\n'
        print '\n'

        # print failure_output_luas
        print 'failure output files:'
        for filename, result in self.failure_output_luas.iteritems():
            print filename, ':\n\t', result, '\n'
        print '\n'

        # print skip excels
        print 'skip excels:'
        for filename in self.skip_excels:
            print filename
        print '\n'

        # pickle excels_mtime_dict
        dict_file = open(self.excels_mtime_dict_file, 'wb')
        pickle.dump(self.excels_mtime_dict, dict_file)
        dict_file.close()

    def run(self):
        self.start()
        self.end()

if __name__ == '__main__':
    argv = sys.argv
    instance = BatchExportLua('.')
    instance.run()
