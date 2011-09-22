#!/usr/bin/python
"""
Copyright 2011 Eric Worden

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pygst
pygst.require('0.10')
gobject.threads_init()
import gst
import curses, getpass, os, readline
import subprocess, sys
from optparse import OptionParser

class SphinxKeys(object):
    """PocketSphinx/GStreamer Keyboard Control Application"""
    def __init__(self):
        parser = OptionParser()
        parser.add_option("-q", "--quiet", dest="quiet", action='store_true', default=False, help="Don't print anything")
        (self.options, args) = parser.parse_args()
        sphinxdir = os.path.dirname(sys.argv[0])
        if sphinxdir == '':
            sphinxdir = '.'
        self.file_macros = None
        paths = [
            os.environ['HOME'] + '/.sphinxkeys/macros',
            '/etc/sphinxkeys/macros',
            sphinxdir + '/macros'
            ]
        for path in paths:
            if not self.file_macros:
                if os.path.exists(path):
                    self.file_macros = path
                    break
        if not self.file_macros:
            print 'Could not find a macro file.'
            sys.exit(1)
        self.file_dictionary = None
        paths = [
            os.environ['HOME'] + '/.sphinxkeys/keyboard.dic',
            '/etc/sphinxkeys/keyboard.dic',
            sphinxdir + '/keyboard.dic'
            ]
        for path in paths:
            if not self.file_dictionary:
                if os.path.exists(path):
                    self.file_dictionary = path
                    break
        if not self.file_dictionary:
            print 'Could not find a dictionary file.'
            sys.exit(1)
        self.file_language_model = None
        paths = [
            os.environ['HOME'] + '/.sphinxkeys/keyboard.lm',
            '/etc/sphinxkeys/keyboard.lm',
            sphinxdir + '/keyboard.lm'
            ]
        for path in paths:
            if not self.file_language_model:
                if os.path.exists(path):
                    self.file_language_model = path
                    break
        if not self.file_language_model:
            print 'Could not find a language model file.'
            sys.exit(1)
        self.init_macros()
        self.init_gui()
        self.init_gst()
        self.responsive = True
        self.last_action = ''

    def init_gui(self):
        """Initialize the GUI components"""
        self.window = gtk.Window()
        self.window.connect("delete-event", gtk.main_quit)
        self.window.set_default_size(150,150)
        self.window.set_border_width(5)
        vbox = gtk.VBox()
        self.textbuf = gtk.TextBuffer()
        self.text = gtk.TextView(self.textbuf)
        self.text.set_wrap_mode(gtk.WRAP_WORD)
        vbox.pack_start(self.text)
        self.button = gtk.ToggleButton("Start listening")
        self.button.connect('clicked', self.button_clicked)
        vbox.pack_start(self.button, False, False, 5)
        self.window.add(vbox)
        self.window.show_all()

    def init_gst(self):
        """Initialize the speech components"""
        self.pipeline = gst.parse_launch('alsasrc ! audioconvert ! audioresample '
                                         + '! vader name=vad auto-threshold=true '
                                         + '! pocketsphinx name=asr ! fakesink')
        asr = self.pipeline.get_by_name('asr')
        asr.set_property('lm', self.file_language_model)
        asr.set_property('dict', self.file_dictionary)
        asr.connect('partial_result', self.asr_partial_result)
        asr.connect('result', self.asr_result)
        asr.set_property('configured', True)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::application', self.application_message)
        self.pipeline.set_state(gst.STATE_PLAYING)

    def init_macros(self):
        """Read macro configuration from file"""
        self.macros = {}
        self.passwords = {}
        self.letters = [
            'ALPHA',
            'BRAVO',
            'CHARLIE',
            'DELTA',
            'ECHO',
            'FOXTROT',
            'GOLF',
            'HOTEL',
            'INDIA',
            'JULIET',
            'KILO',
            'LIMA',
            'MIKE',
            'NOVEMBER',
            'OSCAR',
            'PAPA',
            'QUEBEC',
            'ROMEO',
            'SIERRA',
            'TANGO',
            'UNIFORM',
            'VICTOR',
            'WHISKEY',
            'XRAY',
            'YANKEE',
            'ZULU'
            ]
        self.numbers = {
            'ONE':1,
            'TWO':2,
            'THREE':3,
            'FOUR':4,
            'FIVE':5,
            'SIX':6,
            'SEVEN':7,
            'EIGHT':8,
            'NINE':9,
            'TEN':10,
            'ELEVEN':11,
            'TWELVE':12,
            'TWENTY':20,
            'THIRTY':30
            }
        self.control_keys = [
            'CONTROL',
            'ALTER',
            'SHIFT',
            'START'
            ]
        self.meta_keys = [
            'ESCAPE',
            'HOME',
            'PAGE UP',
            'PAGE DOWN',
            'BACK SPACE',
            'DELETE',
            'END',
            'FOXTROT FOUR',
            'CONTROL',
            'ALTER',
            'SHIFT',
            'CAPS',
            'ARROW DOWN',
            'ARROW UP',
            'ARROW LEFT',
            'ARROW RIGHT',
            'RETURN',
            'TAB'
            ]
        macrorc = open(self.file_macros,'r')
        section = ''
        for line in macrorc:
            line = line.strip()
            if line.startswith('#') == False and line.startswith(' ') == False and len(line) > 0:
                if line == 'section keys':
                    section = 'keys'
                elif line == 'section password':
                    section = 'password'
                else:
                    if section == 'keys':
                        pieces = line.split('=')
                        if len(pieces) == 2:
                            pieces[1] = pieces[1].replace('\\n',"\n")
                            self.macros[pieces[0]] = pieces[1]
                        else:
                            print 'skipped macros line: %s' % line
                    elif section == 'password':
                        self.passwords[line] = 'password'
        macrorc.close()
        if len(self.passwords) > 0:
            self.password_input()
        sp = subprocess
        devnull = open('/dev/null', 'w')
        xmacro = sp.Popen(["xmacroplay", ":0",],stdin=sp.PIPE,stdout=devnull,bufsize=1,close_fds=True)
        self.xmacro_pipe = xmacro.stdin

    def password_input(self):
        """User inputs passwords."""
        for password_key in self.passwords:
            match = False
            while match == False:
                prompt = "\nEnter password for %s: " % password_key
                password1 = getpass.getpass(prompt)
                prompt = "\nConfirm password for %s: " % password_key
                password2 = getpass.getpass(prompt)
                if password1 == password2:
                    match = True
                    self.passwords[password_key] = password1
                    self.macros["PASSWORD " + password_key] = "String %s\n" % password1
                else:
                    print "\nPasswords don't match. Try again."

    def asr_partial_result(self, asr, text, uttid):
        """Forward partial result signals on the bus to the main thread."""
        struct = gst.Structure('partial_result')
        struct.set_value('hyp', text)
        struct.set_value('uttid', uttid)
        asr.post_message(gst.message_new_application(asr, struct))

    def asr_result(self, asr, text, uttid):
        """Forward result signals on the bus to the main thread."""
        struct = gst.Structure('result')
        struct.set_value('hyp', text)
        struct.set_value('uttid', uttid)
        asr.post_message(gst.message_new_application(asr, struct))

    def application_message(self, bus, msg):
        """Receive application messages from the bus."""
        msgtype = msg.structure.get_name()
        if msgtype == 'result':
            self.final_result(msg.structure['hyp'], msg.structure['uttid'])

    def final_result(self, hyp, uttid):
        """Decide what to do with the heard words."""
        result = False
        if not self.options.quiet:
            print 'heard "%s"' % hyp
        word_list = hyp.split()
        word_count = len(word_list)
        if word_count > 0 and word_list[0] == 'PASSWORD':
            try_word = hyp
            result = self.word_run(try_word)
        elif word_count >= 2 and word_list[0] in self.control_keys:
            try_word = hyp
            result = self.word_run(try_word)
        else:
            word_num = 0
            while word_num <= word_count - 1:
                if word_num <= word_count - 2:
                    try_word = word_list[word_num] + " " + word_list[word_num + 1]
                else:
                    try_word = word_list[word_num]
                result = self.word_run(try_word)
                if result == True:
                    word_num = word_num + 1
                elif try_word != word_list[word_num]:
                    try_word = word_list[word_num]
                    result = self.word_run(try_word)
                word_num = word_num + 1
        if result == True:
            strOut = "%s\n" % hyp

    def word_run(self, string):
        """Really do a command."""
        returnVal = False
        action = ''
        is_password = False
        words = string.split(' ')
        if self.responsive == False:
            if string == "ACTION START":
                self.responsive = True
                returnVal = True
        else:
            if words[0] == 'PASSWORD':
                is_password = True
            if words[0] == 'REPEAT':
                action = self.last_action
                self.xmacro_pipe.write(action)
                returnVal = True
            elif string == "ACTION STOP":
                self.responsive = False
                returnVal = True
            elif string == "GOODBYE GOODBYE":
                sys.exit()
            elif words[0] == 'TIMES' and len(words) == 2 and words[1] in self.numbers:
                i = 2
                while i <= self.numbers[words[1]]:
                    self.xmacro_pipe.write(self.last_action)
                    i = i + 1
                returnVal = True
            elif string in self.macros:
                action = self.macros[string]
                self.xmacro_pipe.write(action)
                returnVal = True
            elif words[0] in self.control_keys:
                if len(words) == 2 and words[1] in self.letters:
                    #eg "CONTROL FOXTROT"
                    action = self.macros[words[0] + ' DOWN'] + self.macros[words[1]] + self.macros[words[0] + ' UP']
                    self.xmacro_pipe.write(action)
                    returnVal = True
                else:
                    meta_words = ''
                    for word in words[1:]:
                        meta_words = meta_words + ' ' + word
                    meta_words = meta_words[1:]
                    if meta_words in self.meta_keys:
                        #eg "SHIFT DELETE" or "ALTER FOXTROT FOUR"
                        action = self.macros[words[0] + ' DOWN'] + self.macros[meta_words] + self.macros[words[0] + ' UP']
                        self.xmacro_pipe.write(action)
                        returnVal = True
        if returnVal == True:
            if is_password == True:
                action = ''
            elif action != '':
                self.last_action = action
        return returnVal

    def button_clicked(self, button):
        """Handle button presses."""
        if button.get_active():
            button.set_label("Stop listening")
            self.pipeline.set_state(gst.STATE_PLAYING)
        else:
            button.set_label("Start listening")
            vader = self.pipeline.get_by_name('vad')
            vader.set_property('silent', True)
            self.pipeline.set_state(gst.STATE_PAUSED)

app = SphinxKeys()
gtk.main()
