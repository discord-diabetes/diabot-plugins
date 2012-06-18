###
# Copyright (c) 2012, Andrew Cook, Halley Jacobs, Greg Kitson
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import time as dumbtime
from datetime import *
import os
import re
import supybot.conf as conf
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.ircdb as ircdb
import string


class BGDB_SQLite(object):
	
	def __init__(self, filename):
		self.filename = conf.supybot.directories.data.dirize(filename)
		try:
			import sqlite3 as sqlite
		except ImportError:
			try:
				import sqlite
			except ImportError:
				raise callbacks.Error, 'You need to have PySQLite installed to ' \
							'use BGs.  Download it at ' \
							'<http://code.google.com/p/pysqlite/>'
		if os.path.exists(filename):
			self.db = sqlite.connect(filename)
			cursor = self.db.cursor()
			cursor.execute("PRAGMA foreign_keys = ON")
			self.pruneall()
			return
		self.db = sqlite.connect(filename)
		cursor = self.db.cursor()
		cursor.execute("PRAGMA foreign_keys = ON")
		cursor.execute("CREATE TABLE users(" \
					"uid INTEGER PRIMARY KEY AUTOINCREMENT," \
					"nick TEXT UNIQUE ON CONFLICT IGNORE," \
					"tz STRING DEFAULT \"US/Eastern\"," \
					"mmode INTEGER DEFAULT 0," \
					"rnum INTEGER NOT NULL," \
					"rmode INTEGER NOT NULL)")
		cursor.execute("CREATE TABLE bgs(" \
					"bgid INTEGER PRIMARY KEY AUTOINCREMENT," \
					"uid INTEGER NOT NULL," \
					"test FLOAT NOT NULL," \
					"ts INTEGER NOT NULL," \
					"FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE)")
		cursor.execute("CREATE TABLE tags(" \
					"bgid INTEGER NOT NULL," \
					"tag TEXT NOT NULL," \
					"UNIQUE (bgid, tag) ON CONFLICT IGNORE," \
					"FOREIGN KEY (bgid) REFERENCES bgs(bgid) ON DELETE CASCADE)")
	
	def isruser(self, nick):
		cursor = self.db.cursor()
		cursor.execute("SELECT COUNT(*) FROM users WHERE nick = ?", [nick])
		return (cursor.fetchone()[0] == 1)
	
	def getmeter(self, nick):
		cursor = self.db.cursor()
		cursor.execute("SELECT mmode FROM users WHERE nick = ?", [nick])
		return (cursor.fetchone()[0])
	
	def setmeter(self, nick, meter):
		cursor = self.db.cursor()
		cursor.execute("UPDATE users SET mmode = ? WHERE nick = ?", [meter, nick])
	
	def reguser(self, nick, rnum, rmode):
		if rmode == "days":
			rmode = 1
		elif rmode == "entries":
			rmode = 2
		else:
			raise callbacks.Error, rmode + " is not a valid prune mode."
		cursor = self.db.cursor()
		cursor.execute("INSERT INTO users(nick, rnum, rmode) VALUES(?, ?, ?)", [nick, rnum, rmode])
		cursor.execute("UPDATE users SET rnum = ?, rmode = ? WHERE nick = ?", [rnum, rmode, nick])
		self.db.commit()
	
	def deluser(self, nick):
		cursor = self.db.cursor()
		cursor.execute("DELETE FROM users WHERE nick = ?", [nick])
		#thanks to cascading it also deletes all the BG entries and tags
		self.db.commit()
	
	def addbg(self, nick, test, tags, ts = None):
		if not ts: ts = dumbtime.time()
		cursor = self.db.cursor()
		cursor.execute("INSERT INTO bgs(uid, test, ts) VALUES((SELECT uid FROM users WHERE nick = ?), ?, ?)",
			[nick, test, ts])
		self.db.commit()
		if tags:
			for t in tags:
				cursor.execute("INSERT INTO tags(bgid, tag) VALUES((SELECT bgid FROM bgs " \
					"INNER JOIN users ON bgs.uid = users.uid WHERE nick = ? " \
					"ORDER BY ts DESC LIMIT 1), ?)", [nick, \
					t.translate(string.maketrans("",""), string.punctuation)])
			self.db.commit()
	
	def oopsbg(self, nick):
		cursor = self.db.cursor()
		cursor.execute("DELETE FROM bgs WHERE bgid IN " \
			"(SELECT bgid FROM bgs INNER JOIN users ON bgs.uid = users.uid " \
			"WHERE nick = ? ORDER BY ts DESC LIMIT 1)", [nick])
		self.db.commit()
	
	def getbgs(self, nick, count, tags):
		if not count:
			count = 5
		cursor = self.db.cursor()
		cursor.execute("SELECT bgid, test, ts FROM bgs " \
			"INNER JOIN users ON bgs.uid = users.uid WHERE nick = ? ORDER BY ts DESC", [nick])
		rawreslist = cursor.fetchall()
		reslist = []
		for row in rawreslist:
			cookedrow = {'bgid' : row[0], 'test' : row[1], 'timestamp' : row[2], 'tags' : []}
			cursor.execute("SELECT tag FROM tags WHERE bgid = ?", [row[0]])
			rtags = cursor.fetchall()
			ttags = []
			if tags:
				ttags = tags[:]
			for tag in rtags:
				if tag[0] not in ttags:
					cookedrow['tags'].append(tag[0])
				else:
					ttags.remove(tag[0])
			if ttags and len(ttags):
				continue
			reslist.append(cookedrow)
		if count != 'all':
			reslist = reslist[:count]
		return reslist
	
	def pruneuser(self, nick):
		cursor = self.db.cursor()
		cursor.execute("SELECT * FROM users WHERE nick = ?", [nick])
		user = cursor.fetchone()
		if user[5] == 1: #days
			cursor.execute("DELETE FROM bgs WHERE uid IN (SELECT uid FROM users WHERE nick = ?) " \
				"AND ts < ?", [nick, dumbtime.time() - 86400 * user[4]])
		elif user[5] == 2: #entries
			cursor.execute("DELETE FROM bgs WHERE bgid NOT IN (SELECT bgid FROM bgs " \
				"INNER JOIN users ON bgs.uid = users.uid WHERE nick = ? " \
				"ORDER BY ts DESC LIMIT ?)", [nick, user[4]])
		else: #something I've never seen before
			cursor.execute("DELETE FROM bgs WHERE uid IN (SELECT uid FROM users WHERE nick = ?) " \
				"AND ts < ?", [nick, dumbtime.time() - 86400 * 7]) #make it 7 days by default
		self.db.commit()
	
	def pruneall(self):
		cursor = self.db.cursor()
		cursor.execute("SELECT nick FROM users")
		users = cursor.fetchall()
		for user in users:
			self.pruneuser(user[0])

BGDB = plugins.DB('BGs',
                     {'sqlite3': BGDB_SQLite , 'sqlite': BGDB_SQLite})

class BGs(callbacks.Plugin):
	def __init__(self, irc):
		self.__parent = super(BGs, self)
		self.__parent.__init__(irc)
		self.db = BGDB()
		
	
	def die(self):
		self.__parent.die()
		self.db.db.close()

	def bg(self, irc, msg, args, testlvl, tags):
		"""<glucose test result> [<tag> ...]
		
		Marks a message as a blood glucose reading and gives a conversion.  If you've opted in to saving your 
		information using "bgoptin" you can save notes (listed alphabetically) along with the bg reading. 
		For example, "bg 120 post breakfast" would save "breakfast" and "post" with the blood sugar reading
		of 120. To see a list of bg related commands, use "list BGs".
		"""
		if not self.db.isruser(self._getNick(msg)):
			self._Ubg(irc, msg, args, testlvl)
			if tags and len(tags):
				irc.reply("To save tags, you must opt in. Say \"help bgoptin\" to learn more.")
		else:
			self._Rbg(irc, msg, args, testlvl, tags)
	bg = wrap(bg, ['float', any('lowered')])
	
	def _Ubg(self, irc, msg, args, testlvl):
		msg.tag('bg', testlvl) #to make it easier to find in lastbgs
		if testlvl <= self.registryValue('measurementTransitionValue'):
			irc.reply("{0:.1f} mmol/L = {1:.0f} mg/dL".format(testlvl, testlvl * 18.0182))
		else:
			irc.reply("{0:.0f} mg/dL = {1:.1f} mmol/L".format(testlvl, testlvl / 18.0182))
	
	def _Rbg(self, irc, msg, args, testlvl, tags):
		msg.tag('bg', testlvl) #in case of an opt-out later
		self.db.pruneuser(self._getNick(msg))
		self.db.addbg(self._getNick(msg), testlvl, tags)
		meter = self.db.getmeter(self._getNick(msg))
		if not meter:
			if testlvl <= self.registryValue('measurementTransitionValue'):
				meter = 2
			else:
				meter = 1
			self.db.setmeter(self._getNick(msg), meter)
		if meter == 2:
			irc.reply("{0:.1f} mmol/L = {1:.0f} mg/dL".format(testlvl, testlvl * 18.0182))
		else:
			irc.reply("{0:.0f} mg/dL = {1:.1f} mmol/L".format(testlvl, testlvl / 18.0182))
	
	def last(self, irc, msg, args, count, tags):
		"""[<result count>] [<tag> ...]
		
		Returns the last several blood glucose readings. You can specify how may you want by adding a number 
		after the command. For example, "lastbgs 6" returns the last six blood glucose readings. You can add 
		tags afterward to show only those readings containing those tags; for example, "lastbgs breakfast" 
		returns the last several readings containing the tag "breakfast." All readings are returned in 
		USA Eastern Time.
		"""
		if not self.db.isruser(self._getNick(msg)):
			self._Ulastbgs(irc, msg, args, count)
		else:
			self._Rlastbgs(irc, msg, args, count, tags)
	last = wrap(last, [optional('int'), any('lowered')])
	lastbgs = last
	
	def _Ulastbgs(self, irc, msg, args, count):
		if not count: count = self.registryValue('defaultLastBGCount')
		r = []
		h = reversed(irc.state.history)
		for m in h:
			if len(r) == count:
				break
			if m.nick.lower() == msg.nick.lower() and m.tagged('bg'):
				r.append(m)
		if len(r) == 0:
			irc.reply("Sorry, no BGs on file.")
			return
		f = []
		for m in r:
			s = ""
			now = datetime.now()
			dat = datetime.fromtimestamp(m.tagged('receivedAt'))
			if now - dat > timedelta(7):
				s += dat.strftime("[%b %d %H:%M] ")
			elif now - dat > timedelta(1):
				s += dat.strftime("[%a %H:%M] ")
			else:
				s += dat.strftime("[%H:%M] ")
			if m.tagged('bg') <= self.registryValue('measurementTransitionValue'):
				s += "{0:.1f}".format(m.tagged('bg'))
			else:
				s += "{0:.0f}".format(m.tagged('bg'))
			f.append(s)
		irc.reply(utils.str.commaAndify(f))
		
	def _Rlastbgs(self, irc, msg, args, count, tags):
		def _implode(str, elm):
			return str + ' ' + elm
		self.db.pruneuser(self._getNick(msg))
		if not count: count = self.registryValue('defaultLastBGCount')
		r = self.db.getbgs(self._getNick(msg), count, tags)
		if len(r) == 0:
			if tags:
				irc.reply("Sorry, no BGs with all those tags on file.")
			else:
				irc.reply("Sorry, no BGs on file.")
			return
		f = []
		met = self.db.getmeter(self._getNick(msg))
		for m in r:
			s = ""
			now = datetime.now()
			dat = datetime.fromtimestamp(m['timestamp'])
			if now - dat > timedelta(7):
				s += dat.strftime("[%b %d %H:%M] ")
			elif now - dat > timedelta(1):
				s += dat.strftime("[%a %H:%M] ")
			else:
				s += dat.strftime("[%H:%M] ")
			if met == 2:
				s += "{0:.1f}".format(m['test'])
			elif met == 1:
				s += "{0:.0f}".format(m['test'])
			elif m['test'] <= self.registryValue('measurementTransitionValue'):
				s += "{0:.1f}".format(m['test'])
			else:
				s += "{0:.0f}".format(m['test'])
			if len(m['tags']) > 0:
				s += " (" + reduce(_implode, m['tags']) + ")"
			f.append(s)
		irc.reply(utils.str.commaAndify(f))
	
	def bgoops(self, irc, msg, args):
		"""
		
		Removes the last blood glucose reading from the log, e.g. in case of mistake.
		"""
		if not self.db.isruser(self._getNick(msg)):
			self._Ubgoops(irc, msg, args)
		else:
			self._Rbgoops(irc, msg, args)
	bgoops = wrap(bgoops)
	
	def _Ubgoops(self, irc, msg, args):
		h = reversed(irc.state.history)
		for m in h:
			if m.nick.lower() == msg.nick.lower() and m.tagged('bg'):
				m.tags['bg'] = None
				irc.replySuccess()
				return
		irc.replySuccess()
	
	def _Rbgoops(self, irc, msg, args):
		self.db.oopsbg(self._getNick(msg))
		irc.replySuccess()
		
	def esta1c(self, irc, msg, args, bg):
		"""<bg>
		
		Estimates the results of a glycated hemoglobin (HbA_1C) test given an average blood glucose reading. 
		For example, a consistent 154 mg/dL glucose (8.6 mmol/L) would produce an A1C of 7.0% (51 mmol/mol).
		Americans measure the percent of all hemoglobin that is glycated ("NGSP" or "DCCT", two famous
		clinical trials), while Europeans measure in mmols per mol ("IFCC", a chemistry body).
		"""
		meter = None
		if self.db.isruser(self._getNick(msg)):
			meter = self.db.getmeter(self._getNick(msg))
		if not meter:
			if bg <= self.registryValue('measurementTransitionValue'):
				meter = 2
			else:
				meter = 1
		if meter == 1:
			irc.reply("BG {0:.0f} mg/dL ({1:.1f} mmol/L) ~= A1C {2:.1f}% ({3:.0f} mmol/mol)".format(bg, \
					bg / 18.0182, (bg + 46.7) / 28.7, ((bg + 46.7) / 28.7 - 2.15) * 10.929))
		else:
			irc.reply("BG {0:.1f} mmol/L ({1:.0f} mg/dL) ~= A1C {3:.0f} mmol/mol ({2:.1f}%)".format(bg, \
					bg * 18.0182, (bg + 2.59) / 1.59, ((bg + 2.59) / 1.59 - 2.15) * 10.929))
	esta1c = wrap(esta1c, ['float'])
	ea1c = esta1c
	
	def estbg(self, irc, msg, args, a1c, a1cmode):
		"""<test result> [DCCT|IFCC]
		
		Given the results of a glycated hemoglobin (HbA_1C) test, estimates the average blood glucose level
		over the past 60-90 days. For example, an A1C of 7.0% (51 mmol/L) reflects an average glucose of 
		154 mg/dL (8.6 mmol/L). Please note that the estimation has a very large margin of error.
		Americans measure the percent of all hemoglobin that is glycated ("NGSP" or "DCCT", two famous
		clinical trials), while Europeans measure in mmols per mol ("IFCC", a chemistry body).
		"""
		if a1cmode == None:
			if a1c <= self.registryValue('measurementTransitionValueA1C'):
				a1cmode = 'DCCT'
			else:
				a1cmode = 'IFCC'
		if a1cmode == 'DCCT':
			irc.reply("A1C {0:.1f}% ({1:.0f} mmol/mol) ~= BG {2:.0f} mg/dL ({3:.1f} mmol/L)".format(a1c, \
				(a1c - 2.15) * 10.929, 28.7 * a1c - 46.7, 1.59 * a1c - 2.59))
		else:
			irc.reply("A1C {0:.0f} mmol/mol ({1:.1f}%) ~= BG {2:.1f} mmol/L ({3:.0f} mg/dL)".format(a1c, \
				a1c / 10.929 + 2.15, (a1c / 10.929 + 2.15) * 1.59 - 2.59, \
				(a1c / 10.929 + 2.15) * 28.7 - 46.7))
	estbg = wrap(estbg, ['float', optional(('literal', ('DCCT', 'IFCC')))])
	eag = estbg
	ebg = estbg
	
	def bgoptin(self, irc, msg, args, count, period):
		"""<count> {days|entries}
		
		Begins specifically saving your blood glucose readings for the number of days or entries that you 
		specify. When you list your BGs or enter a new one, expired entries are deleted. For example, 
		"bgoptin 90 days" stores your blood glucose readings for 90 days, after which they are removed. 
		While we try to keep your information safe and private, please note that you opt in at your own risk.
		To remove all your information from the database, use "bgoptout".
		"""
		if self.db.isruser(self._getNick(msg)):
			self.db.reguser(self._getNick(msg), count, period)
			irc.replySuccess()
			return
		self.db.reguser(self._getNick(msg), count, period)
		r = []
		h = reversed(irc.state.history)
		for m in h:
			if m.nick.lower() == msg.nick.lower() and m.tagged('bg'):
				self.db.addbg(self._getNick(msg), m.tagged('bg'), [], m.tagged('receivedAt'))
		self.db.pruneuser(self._getNick(msg))
		irc.replySuccess()
	bgoptin = wrap(bgoptin, ['int', ('literal', ('days','entries'), \
		'You must specify a certain number of days or entries. No exceptions.')])
	
	def bgoptout(self, irc, msg, args):
		"""
		
		Removes all of your blood glucose readings and other information from the database. Only blood 
		glucose readings in the chat history will be accessible after using this command.
		"""
		if not self.db.isruser(self._getNick(msg)):
			irc.replySuccess()
			return
		self.db.deluser(self._getNick(msg))
		irc.replySuccess()
	bgoptout = wrap(bgoptout)
	
	
	
	def _getNick(self, msg):
		try:
			user = ircdb.users.getUser(msg.prefix)
			return user.name.lower()
		except:
			return msg.nick.lower()
	
Class = BGs


# vim:set shiftwidth=8 tabstop=8 noexpandtab textwidth=119:
